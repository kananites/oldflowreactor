#!/usr/bin/env python3
"""
MFC Controller Module for Bronkhorst MFCs
Handles communication and control of individual MFCs
"""

import serial
import time
import struct
from typing import Optional, Dict, Any

# ProPar Protocol Constants
PARAM_TYPE_MAP = {
    'char': 0x00,
    'int': 0x20,
    'float': 0x40,
    'str': 0x60
}

# Parameter definitions from working protocol
PARAM_DEFINITIONS = {
    'measure': {'process': 1, 'fbnr': 0, 'type': 'int'},
    'setpoint': {'process': 1, 'fbnr': 1, 'type': 'int'},
    'fluid_name': {'process': 1, 'fbnr': 17, 'type': 'str', 'len': 10},
    'capacity': {'process': 1, 'fbnr': 13, 'type': 'float'},
    'capacity_unit': {'process': 1, 'fbnr': 31, 'type': 'str', 'len': 7},
}

class MFCController:
    """Controller for individual Bronkhorst MFC using ProPar ASCII protocol"""
    
    def __init__(self, ser: serial.Serial, node_address: int, channel: str, name: str):
        self.ser = ser
        self.node_address = node_address
        self.channel = channel
        self.name = name
        self.capacity = 0.0
        self.capacity_unit = "sccm"
        self.gas_type = "Unknown"
        
        # Initialize with current values
        self._update_capacity_info()
    
    def build_propar_message(self, command: int, process: int, fbnr: int, param_type: str, 
                           value: Optional[Any] = None, str_len: int = 0) -> bytes:
        """Build ProPar ASCII message based on working protocol"""
        # 1. Start with the command byte
        data_bytes = bytearray([command])

        if command == 0x04:  # Read command
            index = 1
            # First process/param block (describes the desired reply format)
            data_bytes.append(process & 0x7F)
            data_bytes.append(PARAM_TYPE_MAP[param_type] | (index & 0x1F))
            # Second process/param block (describes the parameter to read)
            data_bytes.append(process & 0x7F)
            data_bytes.append(PARAM_TYPE_MAP[param_type] | (fbnr & 0x1F))
            if param_type == 'str':
                data_bytes.append(str_len)

        elif command == 0x01:  # Write command
            process_byte = process & 0x7F  # Ensure chaining bit is off
            param_byte = (PARAM_TYPE_MAP[param_type] | (fbnr & 0x1F))
            data_bytes.append(process_byte)
            data_bytes.append(param_byte)
            if param_type == 'int':
                # Values are 16-bit, MSB first
                data_bytes.extend(value.to_bytes(2, 'big'))
            elif param_type == 'float':
                # Floats are 32-bit single-precision (IEEE 754)
                data_bytes.extend(struct.pack('>f', value))
            elif param_type == 'char':
                data_bytes.append(value & 0xFF)
            else: # str
                data_bytes.append(len(value) & 0xFF)
                data_bytes.extend(value.encode('ascii'))

        # Calculate length: node byte + data bytes
        length = 1 + len(data_bytes)

        # Assemble the final message string
        message = f":{length:02X}{self.node_address:02X}{data_bytes.hex().upper()}"
        return (message + '\r\n').encode('ascii')
    
    def parse_propar_response(self, response_bytes: bytes, expected_type: str) -> Optional[Any]:
        """Parse ProPar ASCII response"""
        if not response_bytes:
            return None

        response_str = response_bytes.decode('ascii').strip()
        if not response_str.startswith(':'):
            return None

        # Remove start colon
        response_str = response_str[1:]
        
        # Extract fields
        length = int(response_str[0:2], 16)
        node_id = int(response_str[2:4], 16)
        data_hex = response_str[4:]
        data_bytes = bytes.fromhex(data_hex)
        
        if (1 + len(data_bytes)) != length:
            return None

        command = data_bytes[0]

        # Handle status/error messages (Command 00)
        if command == 0x00:
            status = data_bytes[1]
            if status == 0x00:
                return True
            else:
                return None

        # Handle data response from a read command (Command 02)
        elif command == 0x02:
            value_bytes = data_bytes[3:]
            if expected_type == 'int':
                return int.from_bytes(value_bytes, 'big')
            elif expected_type == 'float':
                return struct.unpack('>f', value_bytes)[0]
            elif expected_type == 'str':
                str_len = value_bytes[0]
                return value_bytes[1:1+str_len].decode('ascii').strip()
        
        return None
    
    def read_parameter(self, param_name: str) -> Optional[Any]:
        """Read a parameter using ProPar ASCII protocol"""
        try:
            if param_name not in PARAM_DEFINITIONS:
                print(f"Unknown parameter: {param_name}")
                return None
            
            p = PARAM_DEFINITIONS[param_name]
            message = self.build_propar_message(
                0x04, p['process'], p['fbnr'], p['type'], str_len=p.get('len', 0)
            )
            
            # Send command
            self.ser.write(message)
            self.ser.flush()
            time.sleep(0.1)
            
            # Read response
            response = self.ser.readline()
            
            # Parse response
            value = self.parse_propar_response(response, p['type'])
            return value
            
        except Exception as e:
            print(f"Error reading parameter {param_name} from {self.name} (node {self.node_address}): {e}")
            return None
    
    def write_parameter(self, param_name: str, value: Any) -> bool:
        """Write a parameter using ProPar ASCII protocol"""
        try:
            if param_name not in PARAM_DEFINITIONS:
                print(f"Unknown parameter: {param_name}")
                return False
                
            p = PARAM_DEFINITIONS[param_name]
            message = self.build_propar_message(
                0x01, p['process'], p['fbnr'], p['type'], value=value
            )
            
            # Send command
            self.ser.write(message)
            self.ser.flush()
            time.sleep(0.1)
            
            # Read response
            response = self.ser.readline()
            
            # Check if write was successful
            result = self.parse_propar_response(response, 'status')
            return result is True
            
        except Exception as e:
            print(f"Error writing parameter {param_name} to {self.name} (node {self.node_address}): {e}")
            return False
    
    def _update_capacity_info(self):
        """Update capacity and gas type information"""
        self.capacity = self.read_parameter('capacity') or 0.0
        self.capacity_unit = self.read_parameter('capacity_unit') or "sccm"
        self.gas_type = self.read_parameter('fluid_name') or "Unknown"
    
    def get_current_flow(self) -> float:
        """Get current flow rate in actual units (sccm)"""
        measure_int = self.read_parameter('measure')
        if measure_int is None:
            return 0.0
        
        # Convert to percentage first, then multiply by capacity to get actual flow rate
        percentage = (measure_int / 32000.0) * 100.0
        return (percentage / 100.0) * self.capacity
    
    def get_current_setpoint(self) -> float:
        """Get current setpoint in actual units (sccm)"""
        setpoint_int = self.read_parameter('setpoint')
        if setpoint_int is None:
            return 0.0
        
        # Convert to percentage first, then multiply by capacity to get actual flow rate
        percentage = (setpoint_int / 32000.0) * 100.0
        return (percentage / 100.0) * self.capacity
    
    def set_flow_rate(self, flow_rate_sccm: float) -> bool:
        """Set flow rate in actual units (sccm)"""
        try:
            # Convert sccm to percentage of capacity
            if self.capacity <= 0:
                print(f"Cannot set flow rate: capacity is {self.capacity}")
                return False
            
            percentage = (flow_rate_sccm / self.capacity) * 100.0
            
            # Ensure percentage is within valid range
            if percentage < 0:
                percentage = 0
            elif percentage > 100:
                percentage = 100
            
            # Convert percentage to integer value (0-32000 range)
            int_value = int(percentage / 100.0 * 32000)
            
            success = self.write_parameter('setpoint', int_value)
            
            if success:
                print(f"{self.name}: Flow setpoint set to {flow_rate_sccm:.2f} sccm ({percentage:.2f}% of {self.capacity} sccm)")
            else:
                print(f"{self.name}: Error setting flow to {flow_rate_sccm:.2f} sccm")
                
            return success
                
        except Exception as e:
            print(f"{self.name}: Error setting flow rate: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get complete status of the MFC"""
        current_flow = self.get_current_flow()
        current_setpoint = self.get_current_setpoint()
        
        return {
            'name': self.name,
            'channel': self.channel,
            'node': self.node_address,
            'gas_type': self.gas_type,
            'capacity': self.capacity,
            'capacity_unit': self.capacity_unit,
            'current_flow': current_flow,
            'current_setpoint': current_setpoint,
            'flow_percentage': (current_flow / self.capacity * 100) if self.capacity > 0 else 0,
            'setpoint_percentage': (current_setpoint / self.capacity * 100) if self.capacity > 0 else 0
        }
