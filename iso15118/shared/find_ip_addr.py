import socket #To get the ip_address
import subprocess #To check the internet connection
import psutil #To get automatically the interfaces configured
import logging

def get_ip_address(interface:str):
    try:
        # Get the IP address of the specified interface
        ip_address = subprocess.check_output(["ip", "addr", "show", interface]).decode("utf-8")
        ip_address = ip_address.split("inet ")[1].split("/")[0]
        return ip_address.strip()
    except subprocess.CalledProcessError:
        return None

def check_internet_access(source_addr:str):
    try:
        # Try to establish a connection to a known external server (e.g., Google DNS)
        socket.create_connection(address=("8.8.8.8", 53), timeout=5, source_address=(source_addr,0))
        return True
    except OSError:
        return False

def ip_address_assign():
    ip_address = ""
    interfaces = psutil.net_if_stats().keys()
    try:
        for interface in interfaces:
            ip_address = get_ip_address(interface)
            if ip_address:
                logging.info(f"Interface {interface}: IP Address {ip_address}")

                if check_internet_access(source_addr=ip_address):
                    logging.info(f"Interface {interface} has internet access.")
                    return ip_address
                else:
                    logging.warning(f"Interface {interface} does not have internet access.")
            else:
                logging.error(f"No IP address found for interface {interface}")
    except Exception as e:
        logging.error(str(e))
    return ip_address