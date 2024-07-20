import asyncio
import logging
import sys

from iso15118.secc import SECCHandler
from iso15118.secc.controller.interface import ServiceStatus
from iso15118.secc.controller.simulator import SimEVSEController
from iso15118.secc.secc_settings import Config
from iso15118.shared.exificient_exi_codec import ExificientEXICodec

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

#ISO 15118 task
async def main():
    """
    Entrypoint function that starts the ISO 15118 code running on
    the SECC (Supply Equipment Communication Controller)
    """
    try:
     #To execute on __init__ function of OCPP client
        config = Config()
        config.load_envs()
        config.print_settings()

        if len(sys.argv) > 1:
            secc_custom_sdp_port = int(sys.argv[1])
            logging.info(f"SECC_SDP_PORT {secc_custom_sdp_port}")
        else: 
            secc_custom_sdp_port = None

        sim_evse_controller = SimEVSEController()
        exi_codec_obj = ExificientEXICodec()

    except Exception as e:
        logging.error(e)
        await asyncio.sleep(1)
    while True:
        try:
            #Task to execute inside the OCPP client
            await sim_evse_controller.set_status(ServiceStatus.STARTING)
            await SECCHandler(
                exi_codec=exi_codec_obj,
                evse_controller=sim_evse_controller,
                config=config
            ).start(config.iface, sdp_custom_port=secc_custom_sdp_port)
        except Exception as e:
            exi_codec_obj.reset_gateway()
            logging.error(e)
            await asyncio.sleep(1)


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("SECC program terminated manually")


if __name__ == "__main__":
    run()
