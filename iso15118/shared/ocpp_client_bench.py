import asyncio
import logging
import time
import csv
import psutil
from datetime import datetime
import uuid
from iso15118.shared.find_ip_addr import ip_address_assign
import sys
import json

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

from dataclasses import is_dataclass

logging.basicConfig(level=logging.ERROR)

def get_dataclass_size(obj):
    """Recursively calculates the size of a dataclass instance."""
    size = sys.getsizeof(obj)
    # Check if it's a dataclass instance before proceeding
    if is_dataclass(obj):
        for field in obj.__dataclass_fields__.values():
            attr = getattr(obj, field.name)
            if isinstance(attr, (list, dict)):
                size += sum(get_dataclass_size(x) for x in attr)
            elif is_dataclass(attr):  # Recursive call for nested dataclasses
                size += get_dataclass_size(attr)
            else:
                size += sys.getsizeof(attr)

    return size

class ChargePoint(cp):
    def __init__(self, charge_point_id, websocket):
        super(cp, self).__init__(charge_point_id, websocket)
        self.experiment = True #Set to TRUE to execute experiments on real the EVSEs

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

        self.evse_id = int(self.my_address.split('.')[-1]) if self.experiment else int(self.cp_id.split('E')[-1])
        self.id_token = uuid.uuid4()
        self.id_token_type = "Local"
        self.connector_status = "Available"
        self._ocpp_active = False
        self._session_authorized = False
        self.transaction_id = None

        self.session_ids = {}

        self.request_authorization = False

        self.eAmount = None
        self.departureTime = None
        self.max_schedule_tuples = None
        self.requestedEnergyTransfer = "AC_single_phase"
        self.evMinCurrent = None
        self.evMaxCurrent = None
        self.evMaxVoltage = None
    
        self.charging_profile = None
        self.start_time_on_set_charging_profile = 0
        self.end_time_on_set_charging_profile = 0
        

        # Initialize IP generator base values
        self.local_ip_addresses = ['127.0.0.1', '0.0.0.0', '192.168.219.15']
        self.local_ip_index = 0
        self.ip_base = ".".join(self.my_address.split('.')[:3])
        self.current_octet = 0

        # Initialize file for benchmarks
        current_time = datetime.now().strftime("%m-%d-%Y")
        self.benchmark_file = f"client_exp_data_for_evse_id_{self.cp_id}_on_{current_time}.csv"
        with open(self.benchmark_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Message", "Latency","Throughput", "CPU_Usage", "Memory_Usage", "TransactionID", "EVSEID", "CPID", "Interval", "CSMSAddress"])

    def record_benchmark(self, message_name, start_time, end_time, total_size):
        latency = end_time - start_time
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.virtual_memory().percent
        throughput = (total_size * 8) / (latency * 1_000_000)
        with open(self.benchmark_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().isoformat(), message_name, latency, throughput, cpu_usage, memory_usage, 
                self.transaction_id, self.evse_id, self.cp_id, self._heartbeat_interval, self.csms_address
            ])
    
    def start_session_benchmark(self, session_id:str, start_time:datetime, ocpp_server_id:str):
        self.session_ids.update({session_id: [start_time, ocpp_server_id]})
    
    def end_session_benchmark(self, session_id, stop_time, energy_requested, evid, ocpp_server_id):
        with open(self.benchmark_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().isoformat(),self.session_ids[session_id] , self.session_ids[session_id][0], stop_time, energy_requested, 
                evid, self.session_ids[session_id][1], ocpp_server_id
            ])
        self.session_ids.pop(session_id)

    
    #Calculate throughput
    """
        #First calculate the total size of the message exchanged
        msg_size = sys.getsizeof(get_dataclass_size(ocpp_request)) + sys.getsizeof(get_dataclass_size(response))
        #Pickup the total latency of the round trip time of the message
        latency = end_time - start_time
        #Calculate the throughput
        ocpp_throughput = (msg_size * 8) / (total_latency * 1_000_000)
    """


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
        ocpp_request =  call.BootNotification(
            charging_station={"model": "Wallbox INESCTEC_TLO", "vendor_name": "INESCTEC"},
            reason="PowerUp",
        )
        response = await self.call(ocpp_request)
        end_time = time.time()
        total_size = sys.getsizeof(get_dataclass_size(ocpp_request)) + sys.getsizeof(get_dataclass_size(response))
        self.record_benchmark("BootNotification", start_time,end_time,total_size)

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
            ocpp_response = await self.call(ocpp_request)
            end_time = time.time()
            total_size = sys.getsizeof(get_dataclass_size(ocpp_request)) + sys.getsizeof(get_dataclass_size(ocpp_response))
            self.record_benchmark("Heartbeat", start_time, end_time, total_size)
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
            ocpp_response = await self.call(ocpp_request)
        elif self._secc_current_state == "SessionStop":
            ocpp_request = call.TransactionEvent(
                event_type="Ended",
                timestamp=str(datetime.now().timestamp()),
                trigger_reason="EnergyLimitReached",
                seq_no=0,
                transaction_info={'transactionId': self.transaction_id, 'chargingState': "SuspendedEV"},
            )
            ocpp_response = await self.call(ocpp_request)
        else:
            ocpp_request = None
        end_time = time.time()
        total_size = sys.getsizeof(get_dataclass_size(ocpp_request)) + sys.getsizeof(get_dataclass_size(ocpp_response))
        self.record_benchmark("TransactionEvent", start_time, end_time, total_size)

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
        end_time = time.time()
        total_size = sys.getsizeof(get_dataclass_size(ocpp_request)) + sys.getsizeof(get_dataclass_size(response))
        self.record_benchmark("StatusNotification", start_time, end_time, total_size)

    async def send_authorize(self):
        start_time = time.time()
        ocpp_request = call.Authorize(id_token={"idToken": str(self.id_token), "type": self.id_token_type})
        response = await self.call(ocpp_request)
        end_time = time.time()
        total_size = sys.getsizeof(get_dataclass_size(ocpp_request)) + sys.getsizeof(get_dataclass_size(response))
        self.record_benchmark("Authorize", start_time, end_time, total_size)
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
            ocpp_request =  call.NotifyEVChargingNeeds(
                charging_needs={'requestedEnergyTransfer': requestedEnergyTransfer,
                                'acChargingParameters': acChargingParameters,
                                'departureTime': str(self.departureTime)},
                evse_id=self.evse_id,
                max_schedule_tuples=int(self.max_schedule_tuples))

            response = await self.call(ocpp_request)
            end_time = time.time()
            total_size = sys.getsizeof(get_dataclass_size(ocpp_request)) + sys.getsizeof(get_dataclass_size(response))
            self.record_benchmark("NotifyEVChargingNeeds", start_time, end_time, total_size)
            await asyncio.sleep(1)
            self.start_time_on_set_charging_profile = time.time()
            return response
    
    @on("SetChargingProfile")
    def on_set_charging_profile(self, evse_id, charging_profile):
        self.end_time_on_set_charging_profile = time.time()
        total_size = sys.getsizeof(json.dumps(evse_id)) + sys.getsizeof(json.dumps(charging_profile))
        """ 
        self.record_benchmark("SetChargingProfile", 
                              self.start_time_on_set_charging_profile, 
                              self.end_time_on_set_charging_profile, 
                              total_size)
        """
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
        
        # Generate the next IP in the sequence within the range .20 to .40
        new_ip = f"{self.ip_base}.{self.current_octet}"
        self.current_octet += 1

        # Reset the current_octet and local_ip_index when wrapping around
        if self.current_octet > 30:
            self.current_octet = 20
            self.local_ip_index = 0
        """
        # Generate the next IP in the sequence
        new_ip = f"{self.ip_base}.{self.current_octet}"
        self.current_octet = (self.current_octet + 1) % 256

        # Reset local IP index when wrapping around
        if self.current_octet == 0:
            self.local_ip_index = 0
        """
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
                f"ws://{csms_addr}:{csms_port}/CP0{self.cp_id}", subprotocols=["ocpp2.0.1"]
            ) as ws:
                self._connection = ws
                # Start the other tasks once the WebSocket connection is established
                start_task = asyncio.create_task(self.start())
                boot_task = asyncio.create_task(self.send_boot_notification())
                # Wait for the tasks to complete
                await asyncio.gather(start_task, boot_task)
        except Exception as e:
            logging.info(str(e))
            timestamp = time.time()
            #self.record_benchmark(str(e), timestamp, timestamp + 0.01, 0)

    
    async def ocpp_cli_routine(self):
        while True:
            self.csms_address, self.ocpp_port = await self.get_csms_address()
            await self.websocket_connection(self.csms_address, self.ocpp_port)
            await asyncio.sleep(0.5)
