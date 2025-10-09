#!/usr/bin/env python3
"""
Comprehensive Bronkhorst MFC diagnostic script
"""

from serial_wrapper import SerialWrapper
import time

def test_serial_connection():
    """Test basic serial connection"""
    print("Testing basic serial connection...")
    try:
        ser = SerialWrapper.create('COM7', 38400)
        print("✓ Serial connection established at 38400 baud")
        
        # Try sending a simple test command
        ser.raw_serial.write(b'\x02\x03\x01\x01\x00\x01\x03\x01\r\n')  # Simple FLOW-BUS command
        response = ser.raw_serial.read(100)
        print(f"Test response: {[hex(x) for x in response]}")
        
        ser.raw_serial.close()
        return True
    except Exception as e:
        print(f"✗ Serial connection failed: {e}")
        return False

def test_different_baud_rates():
    """Test different baud rates"""
    print("\nTesting different baud rates...")
    baud_rates = [9600, 19200, 38400, 57600, 115200]
    
    for baud in baud_rates:
        try:
            print(f"Testing {baud} baud...")
            ser = SerialWrapper.create('COM7', baud)
            
            # Send simple test command
            ser.raw_serial.write(b'\x02\x03\x01\x01\x00\x01\x03\x01')
            response = ser.raw_serial.read(50)
            
            if response:
                print(f"  ✓ {baud} baud: Response {[hex(x) for x in response]}")
            else:
                print(f"  ✗ {baud} baud: No response")
            
            ser.raw_serial.close()
            time.sleep(0.5)
        except Exception as e:
            print(f"  ✗ {baud} baud failed: {e}")

def test_flow_bus_commands():
    """Test various FLOW-BUS commands"""
    print("\nTesting FLOW-BUS commands...")
    
    try:
        ser = SerialWrapper.create('COM7', 38400)
        
        # Test different node addresses and commands
        test_commands = [
            # (address, command, data, description)
            (1, 0x01, [0x00, 0x01], "Read ident from node 1"),
            (2, 0x01, [0x00, 0x01], "Read ident from node 2"),
            (3, 0x01, [0x00, 0x01], "Read ident from node 3"),
            (4, 0x01, [0x00, 0x01], "Read ident from node 4"),
            (5, 0x01, [0x00, 0x01], "Read ident from node 5"),
            (6, 0x01, [0x00, 0x01], "Read ident from node 6"),
            (7, 0x01, [0x00, 0x01], "Read ident from node 7"),
            (8, 0x01, [0x00, 0x01], "Read ident from node 8"),
        ]
        
        for address, command, data, description in test_commands:
            print(f"  {description}...")
            
            # Build packet
            packet = [0x02]  # STX
            packet.append(len(data) + 3)  # Length
            packet.append(address)  # Address
            packet.append(command)  # Command
            packet.extend(data)  # Data
            packet.append(0x03)  # ETX
            
            # Calculate checksum
            checksum = 0
            for byte in packet[1:]:
                checksum ^= byte
            packet.append(checksum)
            
            print(f"    Sending: {[hex(x) for x in packet]}")
            ser.raw_serial.write(bytes(packet))
            
            response = ser.raw_serial.read(100)
            print(f"    Response: {[hex(x) for x in response]}")
            
            if response and len(response) >= 5:
                print(f"    ✓ Got response from node {address}")
            else:
                print(f"    ✗ No response from node {address}")
            
            time.sleep(0.2)
        
        ser.raw_serial.close()
        
    except Exception as e:
        print(f"✗ FLOW-BUS test failed: {e}")

def test_simple_commands():
    """Test simple ASCII commands"""
    print("\nTesting simple ASCII commands...")
    
    try:
        ser = SerialWrapper.create('COM7', 38400)
        
        # Try simple ASCII commands
        commands = [b'?\r\n', b'ID?\r\n', b'STATUS?\r\n', b'HELP\r\n']
        
        for cmd in commands:
            print(f"  Sending: {cmd}")
            ser.raw_serial.write(cmd)
            response = ser.raw_serial.read(100)
            print(f"  Response: {response}")
            time.sleep(0.5)
        
        ser.raw_serial.close()
        
    except Exception as e:
        print(f"✗ ASCII test failed: {e}")

def main():
    print("Bronkhorst MFC Comprehensive Diagnostic")
    print("=" * 50)
    print("This will test various communication methods")
    print()
    
    # Test basic connection
    if test_serial_connection():
        print("\n✓ Basic serial connection works")
        
        # Test different baud rates
        test_different_baud_rates()
        
        # Test FLOW-BUS commands
        test_flow_bus_commands()
        
        # Test simple ASCII commands
        test_simple_commands()
        
    else:
        print("\n✗ Basic serial connection failed")
        print("Check:")
        print("- COM7 is available")
        print("- MFCs are powered on")
        print("- Serial cable is connected")
        print("- No other software is using COM7")
    
    print("\n" + "=" * 50)
    print("DIAGNOSTIC COMPLETE")
    print("If no responses were found, the MFCs might:")
    print("1. Be in a different communication mode")
    print("2. Need configuration mode activation")
    print("3. Use a different protocol than FLOW-BUS")
    print("4. Have different node addresses than expected")

if __name__ == "__main__":
    main()
