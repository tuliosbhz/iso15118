# run_in_parallel.py
import multiprocessing
import subprocess


def run_evcc(config_file, sdp_port):
    subprocess.run(["python3", "iso15118/evcc/main.py", config_file, str(sdp_port)])

if __name__ == "__main__":
    num_processes = 10 #Max of EVCCs simultaneously
    processes = []
    config_file = "iso15118/shared/examples/evcc/iso15118_2/evcc_config_eim_ac.json"
    sdp_port = 15118

    for _ in range(num_processes):
        p_evcc = multiprocessing.Process(target=run_evcc,args=(config_file,sdp_port,))
        p_evcc.start()
        processes.append(p_evcc)
        sdp_port += 1

    for p in processes:
        p.join()
