import numpy as np

def simulate_next_ev_arrival(arrival_rate):
    """
    Simulate the waiting time until the next EV arrival based on the given arrival rate (lambda).
    
    Parameters:
    arrival_rate (float): The average arrival rate (lambda) of EVs per unit time.
    
    Returns:
    float: The time until the next EV arrival.
    """
    waiting_time = np.random.exponential(1 / arrival_rate)
    return waiting_time

# Example usage
#Arrival rate closer to 0.0 will have bigger inter-arrival intervals
#Arrival rate closer to 1.0 will have lower inter-arrival intervals
arrival_rate = 0.1  # Average arrival rate of EVs per unit time

# Simulate the waiting time until the next EV arrival
next_arrival_time = simulate_next_ev_arrival(arrival_rate)
print(f"Waiting time until the next EV arrival: {next_arrival_time:.2f} seconds")
