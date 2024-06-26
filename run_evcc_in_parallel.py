# run_in_parallel.py
import multiprocessing
import subprocess

def run_main():
    subprocess.run(["make", "run-evcc"])

if __name__ == "__main__":
    num_processes = 5 #Max of EVCCs simultaneously
    processes = []

    for _ in range(num_processes):
        p = multiprocessing.Process(target=run_main)
        p.start()
        processes.append(p)

    for p in processes:
        p.join()
