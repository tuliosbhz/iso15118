# run_in_parallel.py
import multiprocessing
import subprocess
import time

def run_secc(sdp_port):
    subprocess.run(["python3", "iso15118/secc/main.py", str(sdp_port)])
if __name__ == "__main__":
    num_processes = 10 #Max of EVCCs simultaneously
    processes = []
    sdp_port = 15118

    for _ in range(num_processes):
        p_secc = multiprocessing.Process(target=run_secc,args=(sdp_port,))
        p_secc.start()
        processes.append(p_secc)
        sdp_port += 1

    for p in processes:
        p.join()
