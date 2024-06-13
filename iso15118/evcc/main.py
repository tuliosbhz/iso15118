import asyncio
import logging
import sys

from iso15118.evcc import Config, EVCCHandler
from iso15118.evcc.controller.simulator import SimEVController
from iso15118.evcc.evcc_config import load_from_file
from iso15118.shared.exificient_exi_codec import ExificientEXICodec

from ev_arrival_sim import simulate_next_ev_arrival

logger = logging.getLogger(__name__)



async def main():
    """
    Entrypoint function that starts the ISO 15118 code running on
    the EVCC (EV Communication Controller)
    """
    while True:
        config = Config()
        config.load_envs()
        if len(sys.argv) > 1:
            ev_config_file_path = sys.argv[1]
            if ev_config_file_path:
                config.ev_config_file_path = ev_config_file_path
        
        evcc_config = await load_from_file(config.ev_config_file_path)
        await EVCCHandler(
            evcc_config=evcc_config,
            iface=config.iface,
            exi_codec=ExificientEXICodec(),
            ev_controller=SimEVController(evcc_config),
        ).start()
        arrival_rate = 0.1
        inter_arrival_inter = simulate_next_ev_arrival(arrival_rate)
        logging.info(f"EVCCsim: Waiting for the next vehicle to plugin in {inter_arrival_inter} s")
        await asyncio.sleep(inter_arrival_inter)


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("EVCC program terminated manually")


if __name__ == "__main__":
    run()
