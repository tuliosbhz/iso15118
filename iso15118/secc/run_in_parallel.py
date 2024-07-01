# run_in_parallel.py
import multiprocessing
import subprocess

def run_main():
    subprocess.run(["python3", "main.py"])

if __name__ == "__main__":
    num_processes = 30 #Max of SECCs simultaneously
    processes = []

    for _ in range(num_processes):
        p = multiprocessing.Process(target=run_main)
        p.start()
        processes.append(p)

    for p in processes:
        p.join()
