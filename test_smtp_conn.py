import socket

host = 'smtp.gmail.com'
port = 587

try:
    print(f"Attempting to connect to {host} on port {port}...")
    # Create a socket object
    s = socket.create_connection((host, port), timeout=5) # 5 second timeout
    print(f"Successfully connected to {host} on port {port}")
    s.close()
except socket.error as e:
    print(f"Failed to connect to {host} on port {port}")
    print(f"Error: {e}")