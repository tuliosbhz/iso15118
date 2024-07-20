import logging
from typing import Optional

from iso15118 import __version__
from iso15118.secc.comm_session_handler import CommunicationSessionHandler
from iso15118.secc.controller.interface import EVSEControllerInterface
from iso15118.secc.secc_settings import Config
from iso15118.shared.iexi_codec import IEXICodec
from iso15118.shared.logging import _init_logger

_init_logger()
logger = logging.getLogger(__name__)


class SECCHandler(CommunicationSessionHandler):
    def __init__(
        self,
        exi_codec: IEXICodec,
        evse_controller: EVSEControllerInterface,
        config: Config,
    ):
        CommunicationSessionHandler.__init__(
            self,
            config,
            exi_codec,
            evse_controller,
        )
    def get_current_state(self):
        # Ensure the dictionary is not empty
        if self.comm_sessions:
            # Get the first key from the dictionary
            first_key = next(iter(self.comm_sessions))
            
            # Retrieve the tuple corresponding to the first key
            first_tuple = self.comm_sessions[first_key]
            
            # Extract the SECCCommunicationSession element from the tuple
            secc_communication_session = first_tuple[0]
            
            # Now you can work with secc_communication_session
            #logger.error(secc_communication_session)
            logger.error(f"CURRENT STATE FROM INIT SECC HANDLER MAIN FILE: {secc_communication_session.current_state}")
        else:
            logger.error("The comm_sessions dictionary is empty.")

    async def start(self, iface: str, start_udp_server: Optional[bool] = True, sdp_custom_port: Optional[int] = None):
        try:
            logger.info(f"Starting 15118 version: {__version__}")
            self.get_current_state()
            await self.start_session_handler(iface, start_udp_server, sdp_custom_port)
        except Exception as exc:
            logger.error(f"SECC terminated: {exc}")
            # Re-raise so the process ends with a non-zero exit code and the
            # watchdog can restart the service
            raise
