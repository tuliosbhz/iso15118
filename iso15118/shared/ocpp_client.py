import asyncio
import logging

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

import asyncio
import logging
from datetime import datetime, timedelta

#from iso15118.secc import SECCHandler
#from iso15118.secc.controller.interface import ServiceStatus
#from iso15118.secc.controller.simulator import SimEVSEController
#from iso15118.secc.secc_settings import Config
#from iso15118.shared.exificient_exi_codec import ExificientEXICodec

import uuid
from iso15118.shared.find_ip_addr import ip_address_assign


#logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.ERROR)

class ChargePoint(cp):

    def __init__(self, charge_point_id, websocket):
        super(cp, self).__init__(charge_point_id, websocket)
        """
        Entrypoint function that starts the ISO 15118 code running on
        the SECC (Supply Equipment Communication Controller)
        """
        self.my_address = ip_address_assign()
        self.csms_address = "127.0.0.1"
        self.csms_base_port = 2914
        self.ocpp_port = self.csms_base_port + 1
        """ 
        SECC states of ISO 15118-2:
            SupportedAppProtocol
            SessionSetup
            ServiceDiscovery
            PaymentServiceSelection
            Authorization
            ChargeParameterDiscovery
            PowerDelivery
            ChargingStatus
            PowerDelivery* (?)
            SessionStop
        """
        self._secc_current_state = "NotStarted"
        self._secc_previous_state = self._secc_current_state
        self._station_booted = False
        self._heartbeat_interval = 10
        self._new_secc_state = False

        self.evse_id = int(self.my_address.split('.')[-1])
        self.id_token = uuid.uuid4()
        self.id_token_type ="Local"
        self.connector_status = "Available"
        self._ocpp_active = False
        self._session_authorized = False
        self.transaction_id = None

        self.request_authorization = False

        #Notify EV charging needs parameters
        self.eAmount : float= None
        self.departureTime: int = None
        self.max_schedule_tuples : int = None
        self.requestedEnergyTransfer = "AC_single_phase"
        self.evMinCurrent : float = None
        self.evMaxCurrent : float = None
        self.evMaxVoltage : float= None
    
        self.charging_profile:dict = None
        self.experiment:bool = False
    
    def update_boot_status(self, new_value:bool):
        print(f"Updating _station_booted from {self._station_booted} to {new_value}")
        self._station_booted = new_value
        print(f"_station_booted is now {self._station_booted}")
        
    def update_new_secc_state(self):
        if self._secc_previous_state == self._secc_current_state:
            self._new_secc_state = False
        else:
            self._new_secc_state = True
            self._secc_previous_state = self._secc_current_state
        print(f"_new_secc_state is now {self._station_booted}")

    async def send_boot_notification(self):
        """
        Use:
            First OCPP message that should be sent
        Function:
            This intiates the communication with the server and 
            triggers the cyclic OCPP heartbeat messages
        Example:
        """
        request = call.BootNotification(
            charging_station={"model": "Wallbox XYZ", "vendor_name": "anewone"},
            reason="PowerUp",
        )
        response = await self.call(request)
        print(response.custom_data)
        self._heartbeat_interval = response.interval

        if response.status == "Accepted":
            print("Connected to central system.")
            self.update_boot_status(True)
            ocpp_msgs_task = asyncio.create_task(self.send_ocpp_message())
            heartbeat_task = asyncio.create_task(self.send_heartbeat(self._heartbeat_interval))
            await asyncio.gather(heartbeat_task, ocpp_msgs_task)
        elif response.status == "Rejected":
            await self._connection.close()

    async def send_heartbeat(self, interval):
        """
        Use: 
            This method should be an asyncio task triggered 
            inside BootNotification method
        Function:
            It checks the liveness of the client for the server and 
            sync time between them
        Example: 
            
        """
        ocpp_request = call.Heartbeat()
        while True:
            await self.call(ocpp_request)
            await asyncio.sleep(interval)
    
    async def send_ocpp_message(self):
        """
        Abstract design pattern method

        Use: 
            This method should be an asyncio task
        Function:
            It calls all ocpp messages implemented every time
            but the message only will be really sent if the internal 
            conditions of each method of the message is true
        Example: 
            In a new EV connection only the status_notification 
            and transaction_event messages will be sent
        """
        self.update_new_secc_state()
        if self._station_booted:
            await self.send_status_notification()
            await self.send_transaction_event()
            #await self.send_authorize()
            await self.send_notify_ev_charging_needs()

    
    async def send_transaction_event(self):
        if self.transaction_id == None:
            self.transaction_id = "LOC001"
        if self._secc_current_state == "SessionSetup":
            ocpp_request = call.TransactionEvent(
                event_type="Started",
                timestamp=str(datetime.now().timestamp()),
                trigger_reason="EVDetected",
                seq_no=0,
                transaction_info={'transactionId': self.transaction_id, 'chargingState':"EVConnected"},
            )
            response = await self.call(ocpp_request)
        elif self._secc_current_state == "SessionStop":
            ocpp_request = call.TransactionEvent(
                event_type="Ended",
                timestamp=str(datetime.now().timestamp()),
                trigger_reason="EnergyLimitReached",
                seq_no=0,
                transaction_info={'transactionId': self.transaction_id, 'chargingState':"SuspendedEV"},
            )
            response = await self.call(ocpp_request)
        else:
            ocpp_request = None
            


    async def send_status_notification(self):
        if "SupportedAppProtocol" in self._secc_current_state:
            self.connector_status = "Occupied"
            ocpp_request = call.StatusNotification(timestamp=datetime.now().strftime('%Y-%m-%d T %H:%M:%S '),
                                            connector_status=self.connector_status, 
                                            evse_id = self.evse_id, 
                                            connector_id = 1)
            response = await self.call(ocpp_request)
        elif "SessionStop" in self._secc_current_state :
            self.connector_status = "Available"
            ocpp_request = call.StatusNotification(timestamp=datetime.now().strftime('%Y-%m-%d T %H:%M:%S '),
                                            connector_status=self.connector_status, 
                                            evse_id = self.evse_id, 
                                            connector_id = 1)
            response = await self.call(ocpp_request)
        else:
            ocpp_request=None
            

    async def send_authorize(self):
        ocpp_request = call.Authorize(id_token={ "idToken": str(self.id_token), "type": self.id_token_type})
        response = await self.call(ocpp_request)
        if response.id_token_info['status'] == 'Accepted':
            self._session_authorized = True
        else:
            self._session_authorized = False
            logging.warning("AUTHENTICATION FAILED: TOKEN NOT ACCEPTED BY CSMS")
        return self._session_authorized
    
    async def update_ev_charging_needs(self, eAmount,departureTime, max_schedule_tuples,
                                        evMinCurrent,evMaxCurrent,evMaxVoltage):
        self.eAmount = eAmount
        self.departureTime = departureTime
        self.max_schedule_tuples = max_schedule_tuples
        self.evMinCurrent = evMinCurrent
        self.evMaxCurrent = evMaxCurrent
        self.evMaxVoltage = evMaxVoltage

    async def send_notify_ev_charging_needs(self):
        if self.eAmount:
            self.max_schedule_tuples = 1
            requestedEnergyTransfer = "AC_single_phase"
            acChargingParameters={'energyAmount': self.eAmount, 
                                    'evMinCurrent': int(self.evMinCurrent), 
                                    'evMaxCurrent': int(self.evMaxCurrent), 
                                    'evMaxVoltage' : int(self.evMaxVoltage)}
            request=call.NotifyEVChargingNeeds(
                charging_needs={'requestedEnergyTransfer': requestedEnergyTransfer, 
                                'acChargingParameters' : acChargingParameters, 
                                'departureTime': str(self.departureTime)},
                evse_id=self.evse_id,
                max_schedule_tuples=int(self.max_schedule_tuples))

            response = await self.call(request)

            await asyncio.sleep(1)

            return response
    
    @on("SetChargingProfile")
    def on_set_charging_profile(self,evse_id,charging_profile):
        logging.info(f"Received charging profile from CSMS; {charging_profile}")
        if evse_id == self.evse_id:
            self.charging_profile = charging_profile
        return call_result.SetChargingProfile(status="Accepted")
    
    def ip_generator(self):
        # Initialize the base IP address and starting octet if not already done
        if not hasattr(self.ip_generator, "base_ip"):
            self.my_address = ip_address_assign()
            self.ip_generator.base_ip = ".".join(self.my_address.split('.')[:3])
            self.ip_generator.current_octet = 0
        
        # Generate the new IP address
        new_ip = f"{self.ip_generator.base_ip}.{self.ip_generator.current_octet}"
        
        # Update the current octet for the next call
        self.ip_generator.current_octet += 1

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