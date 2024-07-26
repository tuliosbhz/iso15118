import asyncio
import logging
import sys
import argparse

from iso15118.evcc import Config, EVCCHandler
from iso15118.evcc.controller.simulator import SimEVController
from iso15118.evcc.evcc_config import load_from_file
from iso15118.shared.exificient_exi_codec import ExificientEXICodec
import gc

from ev_arrival_sim import simulate_next_ev_arrival

logger = logging.getLogger(__name__)



async def main():
    """
    Entrypoint function that starts the ISO 15118 code running on
    the EVCC (EV Communication Controller)
    """
    try: 
        config = Config()
        config.load_envs()
        if len(sys.argv) > 1:
            ev_config_file_path = sys.argv[1]
            if ev_config_file_path:
                config.ev_config_file_path = ev_config_file_path
        
        evcc_config = await load_from_file(config.ev_config_file_path)
        exi_codec_obj = ExificientEXICodec()
        ev_controller_obj =SimEVController(evcc_config)

        if len(sys.argv) > 2:
            secc_custom_sdp_port = int(sys.argv[2])
            logging.info(f"SECC_SDP_PORT {secc_custom_sdp_port} s")
        else: 
            secc_custom_sdp_port = None
    except Exception as e:
        logging.error(e)
        await asyncio.sleep(2)
    while True:
        try:
            evcc_handler_obj = EVCCHandler(
                evcc_config=evcc_config,
                iface=config.iface,
                exi_codec=exi_codec_obj,
                ev_controller=ev_controller_obj,
                secc_sdp_port=secc_custom_sdp_port,
            )
            await evcc_handler_obj.start()
            del evcc_handler_obj
            gc.collect()
            arrival_rate = 0.001
            inter_arrival_inter = simulate_next_ev_arrival(arrival_rate)
            logging.info(f"EVCCsim: Waiting for the next vehicle to plugin in {inter_arrival_inter} s")

            await asyncio.sleep(inter_arrival_inter)
        except Exception as e:
            logging.error(e)
            await asyncio.sleep(2)

def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("EVCC program terminated manually")


if __name__ == "__main__":
    run()
