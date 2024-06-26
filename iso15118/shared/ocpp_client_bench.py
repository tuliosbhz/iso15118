import asyncio
import logging
import time
import csv
import psutil
from datetime import datetime
import uuid
from iso15118.shared.find_ip_addr import ip_address_assign

try:
    import websockets
except ModuleNotFoundError:
    print("This example relies on the 'websockets' package.")
    print("Please install it by running: ")
    print()
    print(" $ pip install websockets")
    import sys

    sys.exit(1)

from ocpp.routing import on, after
from ocpp.v201 import ChargePoint as cp
from ocpp.v201 import call, call_result

logging.basicConfig(level=logging.INFO)

class ChargePoint(cp):
    def __init__(self, charge_point_id, websocket):
        super(cp, self).__init__(charge_point_id, websocket)
        self.cp_id = charge_point_id
        self.my_address = ip_address_assign()
        self.csms_address = "127.0.0.1"
        self.csms_base_port = 2914 #Configured manually for experiment
        self.ocpp_port = self.csms_base_port + 1
        self._secc_current_state = "NotStarted"
        self._secc_previous_state = self._secc_current_state
        self._station_booted = False
        self._heartbeat_interval = 10
        self._new_secc_state = False

        self.evse_id = int(self.my_address.split('.')[-1])
        self.id_token = uuid.uuid4()
        self.id_token_type = "Local"
        self.connector_status = "Available"
        self._ocpp_active = False
        self._session_authorized = False
        self.transaction_id = None

        self.request_authorization = False

        self.eAmount = None
        self.departureTime = None
        self.max_schedule_tuples = None
        self.requestedEnergyTransfer = "AC_single_phase"
        self.evMinCurrent = None
        self.evMaxCurrent = None
        self.evMaxVoltage = None
    
        self.charging_profile = None
        self.experiment = False #Set to true to execute experiments on real EVSEs

        # Initialize IP generator base values
        self.local_ip_addresses = ['127.0.0.1', '0.0.0.0']
        self.local_ip_index = 0
        self.ip_base = ".".join(self.my_address.split('.')[:3])
        self.current_octet = 0

        # Initialize file for benchmarks
        current_time = datetime.now().strftime("%m-%d-%Y")
        self.benchmark_file = f"client_benchmarks_{current_time}.csv"
        with open(self.benchmark_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Message", "Latency", "CPU_Usage", "Memory_Usage", "TransactionID", "EVSEID", "CPID", "Interval", "CSMSAddress"])

    def record_benchmark(self, message, start_time):
        latency = time.time() - start_time
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.virtual_memory().percent
        with open(self.benchmark_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().isoformat(), message, latency, cpu_usage, memory_usage, 
                self.transaction_id, self.evse_id, self.cp_id, self._heartbeat_interval, self.csms_address
            ])

    def update_boot_status(self, new_value: bool):
        self._station_booted = new_value

    def update_new_secc_state(self):
        if self._secc_previous_state == self._secc_current_state:
            self._new_secc_state = False
        else:
            self._new_secc_state = True
            self._secc_previous_state = self._secc_current_state

    async def send_boot_notification(self):
        start_time = time.time()
        request = call.BootNotification(
            charging_station={"model": "Wallbox XYZ", "vendor_name": "anewone"},
            reason="PowerUp",
        )
        response = await self.call(request)
        self.record_benchmark("BootNotification", start_time)
        print(response.custom_data)
        self._heartbeat_interval = response.interval

        if response.status == "Accepted":
            print("Connected to central system.")
            self.update_boot_status(True)
            heartbeat_task = asyncio.create_task(self.send_heartbeat(self._heartbeat_interval))
            await asyncio.sleep(0.5)
        elif response.status == "Rejected":
            await self._connection.close()

    async def send_heartbeat(self, interval):
        ocpp_request = call.Heartbeat()
        while True:
            start_time = time.time()
            await self.call(ocpp_request)
            self.record_benchmark("Heartbeat", start_time)
            await asyncio.sleep(interval)

    async def send_transaction_event(self):
        start_time = time.time()
        if self.transaction_id is None:
            self.transaction_id = "LOC_" + datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
        if self._secc_current_state == "SessionSetup":
            ocpp_request = call.TransactionEvent(
                event_type="Started",
                timestamp=str(datetime.now().timestamp()),
                trigger_reason="EVDetected",
                seq_no=0,
                transaction_info={'transactionId': self.transaction_id, 'chargingState': "EVConnected"},
            )
            response = await self.call(ocpp_request)
        elif self._secc_current_state == "SessionStop":
            ocpp_request = call.TransactionEvent(
                event_type="Ended",
                timestamp=str(datetime.now().timestamp()),
                trigger_reason="EnergyLimitReached",
                seq_no=0,
                transaction_info={'transactionId': self.transaction_id, 'chargingState': "SuspendedEV"},
            )
            response = await self.call(ocpp_request)
        else:
            ocpp_request = None
        self.record_benchmark("TransactionEvent", start_time)

    async def send_status_notification(self):
        start_time = time.time()
        if "SupportedAppProtocol" in self._secc_current_state:
            self.connector_status = "Occupied"
            ocpp_request = call.StatusNotification(timestamp=datetime.now().strftime('%Y-%m-%d T %H:%M:%S '),
                                                   connector_status=self.connector_status,
                                                   evse_id=self.evse_id,
                                                   connector_id=1)
            response = await self.call(ocpp_request)
        elif "SessionStop" in self._secc_current_state:
            self.connector_status = "Available"
            ocpp_request = call.StatusNotification(timestamp=datetime.now().strftime('%Y-%m-%d T %H:%M:%S '),
                                                   connector_status=self.connector_status,
                                                   evse_id=self.evse_id,
                                                   connector_id=1)
            response = await self.call(ocpp_request)
        else:
            ocpp_request = None
        self.record_benchmark("StatusNotification", start_time)

    async def send_authorize(self):
        start_time = time.time()
        ocpp_request = call.Authorize(id_token={"idToken": str(self.id_token), "type": self.id_token_type})
        response = await self.call(ocpp_request)
        self.record_benchmark("Authorize", start_time)
        if response.id_token_info['status'] == 'Accepted':
            self._session_authorized = True
        else:
            self._session_authorized = False
            logging.warning("AUTHENTICATION FAILED: TOKEN NOT ACCEPTED BY CSMS")
        return self._session_authorized

    async def update_ev_charging_needs(self, eAmount, departureTime, max_schedule_tuples,
                                       evMinCurrent, evMaxCurrent, evMaxVoltage):
        self.eAmount = eAmount
        self.departureTime = departureTime
        self.max_schedule_tuples = max_schedule_tuples
        self.evMinCurrent = evMinCurrent
        self.evMaxCurrent = evMaxCurrent
        self.evMaxVoltage = evMaxVoltage

    async def send_notify_ev_charging_needs(self):
        start_time = time.time()
        if self.eAmount:
            self.max_schedule_tuples = 1
            requestedEnergyTransfer = "AC_single_phase"
            acChargingParameters = {'energyAmount': self.eAmount,
                                    'evMinCurrent': int(self.evMinCurrent),
                                    'evMaxCurrent': int(self.evMaxCurrent),
                                    'evMaxVoltage': int(self.evMaxVoltage)}
            request = call.NotifyEVChargingNeeds(
                charging_needs={'requestedEnergyTransfer': requestedEnergyTransfer,
                                'acChargingParameters': acChargingParameters,
                                'departureTime': str(self.departureTime)},
                evse_id=self.evse_id,
                max_schedule_tuples=int(self.max_schedule_tuples))

            response = await self.call(request)
            self.record_benchmark("NotifyEVChargingNeeds", start_time)
            await asyncio.sleep(1)

            return response
    
    @on("SetChargingProfile")
    def on_set_charging_profile(self, evse_id, charging_profile):
        logging.info(f"Received charging profile from CSMS; {charging_profile}")
        if evse_id == self.evse_id:
            self.charging_profile = charging_profile
        return call_result.SetChargingProfile(status="Accepted")
    
    def ip_generator(self):
        # Check if we need to return a local IP address
        if self.local_ip_index < len(self.local_ip_addresses):
            new_ip = self.local_ip_addresses[self.local_ip_index]
            self.local_ip_index += 1
            return new_ip

        # Generate the next IP in the sequence
        new_ip = f"{self.ip_base}.{self.current_octet}"
        self.current_octet = (self.current_octet + 1) % 256

        # Reset local IP index when wrapping around
        if self.current_octet == 0:
            self.local_ip_index = 0

        return new_ip
    
    async def get_csms_address(self):
        if self.experiment: #Fixed port in different devices
            if self.my_address:
                self.csms_address = self.ip_generator()
            else:
                self.my_address = ip_address_assign()
            self.ocpp_port = self.csms_base_port
        else:
            if self.ocpp_port > 2920:
                self.ocpp_port = 2910
            else:
                self.ocpp_port += 1
        
        return self.csms_address, self.ocpp_port

    async def websocket_connection(self, csms_addr, csms_port):
        try:
            async with websockets.connect(
                f"ws://{csms_addr}:{csms_port}/CP0{csms_port}", subprotocols=["ocpp2.0.1"]
            ) as ws:
                self._connection = ws
                # Start the other tasks once the WebSocket connection is established
                start_task = asyncio.create_task(self.start())
                boot_task = asyncio.create_task(self.send_boot_notification())
                # Wait for the tasks to complete
                await asyncio.gather(start_task, boot_task)
        except Exception as e:
            logging.info(str(e))
    
    async def ocpp_cli_routine(self):
        while True:
            self.csms_address, self.ocpp_port = await self.get_csms_address()
            await self.websocket_connection(self.csms_address, self.ocpp_port)
            await asyncio.sleep(0.01)
