"""
Protocol server implementations following SOLID principles.
Each server class has a Single Responsibility and implements the ProtocolServer interface.
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from abc import ABC

from interfaces import ProtocolServer

logger = logging.getLogger("ProtocolServers")


class ModbusServer(ProtocolServer):
    """
    Modbus TCP Server implementation (SRP - only handles Modbus protocol).
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5020):
        self._host = host
        self._port = port
        self._context = None
        self._store = None
        self._thread: Optional[threading.Thread] = None
        self._points: Dict[str, int] = {}  # name -> register address
        self._register_counter = 0
        self._running = False
        
    def _initialize_datastore(self):
        """Initialize Modbus datastore."""
        from pymodbus.datastore import (
            ModbusSequentialDataBlock, 
            ModbusServerContext,
            ModbusSlaveContext
        )
        
        self._store = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0, [0] * 100),
            co=ModbusSequentialDataBlock(0, [0] * 100),
            hr=ModbusSequentialDataBlock(0, [0] * 10000),
            ir=ModbusSequentialDataBlock(0, [0] * 10000)
        )
        self._context = ModbusServerContext(slaves=self._store, single=True)
    
    def start(self) -> None:
        """Start the Modbus server in a background thread."""
        from pymodbus.server import StartTcpServer
        
        if self._context is None:
            self._initialize_datastore()
        
        self._running = True
        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True
        )
        self._thread.start()
        logger.info(f"Modbus TCP Server started on {self._host}:{self._port}")
    
    def _run_server(self):
        """Run the Modbus server (blocking)."""
        from pymodbus.server import StartTcpServer
        StartTcpServer(context=self._context, address=(self._host, self._port))
    
    def stop(self) -> None:
        """Stop the Modbus server."""
        self._running = False
        # Note: pymodbus StartTcpServer doesn't have clean shutdown
        logger.info("Modbus server stop requested")
    
    def register_point(self, name: str, initial_value: float, writable: bool = False) -> None:
        """Register a point and assign it a register address."""
        if self._store is None:
            self._initialize_datastore()
            
        self._points[name] = self._register_counter
        self._store.setValues(3, self._register_counter, [int(initial_value * 100)])
        self._register_counter += 1
    
    def update_point(self, name: str, value: float) -> None:
        """Update a Modbus register value."""
        if name in self._points and self._store:
            register_addr = self._points[name]
            self._store.setValues(3, register_addr, [int(value * 100)])
    
    def get_point(self, name: str) -> float:
        """Get a point's value from Modbus registers."""
        if name in self._points and self._store:
            register_addr = self._points[name]
            values = self._store.getValues(3, register_addr, 1)
            return values[0] / 100.0 if values else 0.0
        return 0.0


class BACnetServer(ProtocolServer):
    """
    BACnet/IP Server implementation (SRP - only handles BACnet protocol).
    Supports Analog Value (AV), Analog Input (AI), Analog Output (AO),
    Binary Value (BV), Binary Input (BI), and Binary Output (BO) objects.
    """
    
    def __init__(self, device_name: str = "CampusGateway", 
                 device_id: int = 9999, 
                 address: str = "0.0.0.0/24",
                 override_callback=None):
        self._device_name = device_name
        self._device_id = device_id
        self._address = address
        self._app = None
        self._thread: Optional[threading.Thread] = None
        self._points: Dict[str, Any] = {}
        self._point_paths: Dict[str, str] = {}  # object_name -> point_path for overrides
        self._av_counter = 0
        self._ai_counter = 0
        self._ao_counter = 0
        self._bv_counter = 0
        self._bi_counter = 0
        self._bo_counter = 0
        self._override_callback = override_callback  # Callback for write operations
    
    def _initialize_app(self):
        """Initialize BACnet application."""
        from bacpypes.app import BIPSimpleApplication
        from bacpypes.local.device import LocalDeviceObject
        
        local_device = LocalDeviceObject(
            objectName=self._device_name,
            objectIdentifier=self._device_id,
            maxApduLengthAccepted=1024,
            segmentationSupported='segmentedBoth',
            vendorIdentifier=15
        )
        self._app = BIPSimpleApplication(local_device, self._address)
    
    def start(self) -> None:
        """Start the BACnet server in a background thread."""
        from bacpypes.core import run as bacpypes_run
        
        if self._app is None:
            self._initialize_app()
        
        self._thread = threading.Thread(target=bacpypes_run, daemon=True)
        self._thread.start()
        logger.info(f"BACnet Server started on {self._address}")
    
    def stop(self) -> None:
        """Stop the BACnet server."""
        from bacpypes.core import stop as bacpypes_stop
        bacpypes_stop()
        logger.info("BACnet server stop requested")
    
    def register_point(self, name: str, initial_value: float, writable: bool = False, 
                       point_path: str = None, object_type: str = 'AV', instance_number: int = None) -> None:
        """Register a BACnet object.
        
        Args:
            name: Object name
            initial_value: Initial present value
            writable: Whether the point accepts writes
            point_path: Path for override manager (e.g., "central_plant/chiller_1/status")
            object_type: BACnet object type - 'AV', 'AI', 'AO', 'BV', 'BI', 'BO'
            instance_number: Optional specific instance number
        """
        if self._app is None:
            self._initialize_app()
        
        obj = None
        
        if object_type == 'AV':
            from bacpypes.object import AnalogValueObject
            if instance_number is not None:
                oid = instance_number
            else:
                self._av_counter += 1
                oid = self._av_counter
            
            obj = AnalogValueObject(
                objectIdentifier=('analogValue', oid),
                objectName=name,
                presentValue=float(initial_value),
                statusFlags=[0, 0, 0, 0],
            )
        elif object_type == 'AI':
            from bacpypes.object import AnalogInputObject
            if instance_number is not None:
                oid = instance_number
            else:
                self._ai_counter += 1
                oid = self._ai_counter
                
            obj = AnalogInputObject(
                objectIdentifier=('analogInput', oid),
                objectName=name,
                presentValue=float(initial_value),
                statusFlags=[0, 0, 0, 0],
            )
        elif object_type == 'AO':
            from bacpypes.object import AnalogOutputObject
            if instance_number is not None:
                oid = instance_number
            else:
                self._ao_counter += 1
                oid = self._ao_counter
                
            obj = AnalogOutputObject(
                objectIdentifier=('analogOutput', oid),
                objectName=name,
                presentValue=float(initial_value),
                statusFlags=[0, 0, 0, 0],
            )
        elif object_type == 'BV':
            from bacpypes.object import BinaryValueObject
            if instance_number is not None:
                oid = instance_number
            else:
                self._bv_counter += 1
                oid = self._bv_counter
                
            obj = BinaryValueObject(
                objectIdentifier=('binaryValue', oid),
                objectName=name,
                presentValue='active' if initial_value else 'inactive',
                statusFlags=[0, 0, 0, 0],
            )
        elif object_type == 'BI':
            from bacpypes.object import BinaryInputObject
            if instance_number is not None:
                oid = instance_number
            else:
                self._bi_counter += 1
                oid = self._bi_counter
                
            obj = BinaryInputObject(
                objectIdentifier=('binaryInput', oid),
                objectName=name,
                presentValue='active' if initial_value else 'inactive',
                statusFlags=[0, 0, 0, 0],
            )
        elif object_type == 'BO':
            from bacpypes.object import BinaryOutputObject
            if instance_number is not None:
                oid = instance_number
            else:
                self._bo_counter += 1
                oid = self._bo_counter
                
            obj = BinaryOutputObject(
                objectIdentifier=('binaryOutput', oid),
                objectName=name,
                presentValue='active' if initial_value else 'inactive',
                statusFlags=[0, 0, 0, 0],
            )
        else:
            logger.warning(f"Unknown BACnet object type: {object_type}")
            return
        
        if obj:
            self._app.add_object(obj)
            self._points[name] = obj
            if point_path:
                self._point_paths[name] = point_path
    
    def update_point(self, name: str, value: float) -> None:
        """Update a BACnet point's present value."""
        if name in self._points:
            obj = self._points[name]
            obj_type = obj.objectIdentifier[0]
            
            if obj_type in ('binaryValue', 'binaryInput', 'binaryOutput'):
                obj.presentValue = 'active' if value else 'inactive'
            else:
                obj.presentValue = float(value)
    
    def get_point(self, name: str) -> float:
        """Get a BACnet point's present value."""
        if name in self._points:
            obj = self._points[name]
            obj_type = obj.objectIdentifier[0]
            
            if obj_type in ('binaryValue', 'binaryInput', 'binaryOutput'):
                return 1.0 if obj.presentValue == 'active' else 0.0
            return float(obj.presentValue)
        return 0.0
    
    def write_point(self, name: str, value: float, priority: int = 8) -> bool:
        """Write a value to a BACnet point (applies override via callback)."""
        if name not in self._points:
            logger.warning(f"BACnet write to unknown point: {name}")
            return False
        
        point_path = self._point_paths.get(name)
        if point_path and self._override_callback:
            try:
                self._override_callback(point_path, value, priority)
                logger.info(f"BACnet write: {name} = {value} @ priority {priority}")
                return True
            except Exception as e:
                logger.error(f"BACnet write error: {e}")
                return False
        else:
            # Direct update if no override callback
            self.update_point(name, value)
            return True
    
    @property
    def point_count(self) -> int:
        """Return total number of registered points."""
        return len(self._points)




class BACnetSCHub(ProtocolServer):
    """
    BACnet/SC (Secure Connect) WebSocket Hub implementation.
    Provides a WSS endpoint for secure BACnet communication.
    Serves real simulation data from the engine.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8443, engine=None, override_callback=None):
        self._host = host
        self._port = port
        self._engine = engine  # Reference to CampusEngine for real data
        self._override_callback = override_callback  # For write operations
        self._clients: Dict[str, Any] = {}  # client_id -> websocket
        self._devices: Dict[int, Dict] = {}  # device_id -> device info
        self._running = False
        self._server = None
        self._thread = None
        self._point_map = []
        
    def set_engine(self, engine):
        """Set the engine reference (for late binding)."""
        self._engine = engine
        self._refresh_point_map()
        
    def _refresh_point_map(self):
        """Build a linear map of points to instance IDs."""
        if not self._engine:
            return
            
        self._point_map = []
        eng = self._engine
        
        # 0: OAT
        self._point_map.append({'path': 'campus/oat', 'name': 'Outside Air Temp'})
        
        # 1: Electrical kW
        self._point_map.append({'path': 'electrical/main_meter_kw', 'name': 'Main Meter kW'})
        
        # 2: Electrical kWh
        self._point_map.append({'path': 'electrical/main_meter_kwh', 'name': 'Main Meter kWh'})
        
        # Central Plant
        if eng.central_plant:
            for ch in eng.central_plant.chillers:
                prefix = f'central_plant/chiller_{ch.id}'
                self._point_map.append({'path': f'{prefix}/chw_supply_temp', 'name': f'Chiller {ch.id} Supply Temp'})
                self._point_map.append({'path': f'{prefix}/chw_return_temp', 'name': f'Chiller {ch.id} Return Temp'})
                self._point_map.append({'path': f'{prefix}/load_percent', 'name': f'Chiller {ch.id} Load %'})
        
        # Buildings
        for bldg in eng.buildings:
            for ahu in bldg.ahus:
                prefix = f'building_{bldg.id}/ahu_{ahu.id}'
                self._point_map.append({'path': f'{prefix}/supply_temp', 'name': f'{bldg.name} {ahu.name} Supply Temp'})
                self._point_map.append({'path': f'{prefix}/return_temp', 'name': f'{bldg.name} {ahu.name} Return Temp'})
                self._point_map.append({'path': f'{prefix}/fan_speed', 'name': f'{bldg.name} {ahu.name} Fan Speed'})
                
                for vav in ahu.vavs:
                    vav_prefix = f'{prefix}/vav_{vav.id}'
                    self._point_map.append({'path': f'{vav_prefix}/room_temp', 'name': f'{vav.zone_name} Room Temp'})
                    self._point_map.append({'path': f'{vav_prefix}/airflow', 'name': f'{vav.zone_name} Airflow'})

    def set_override_callback(self, callback):
        """Set the override callback for write operations."""
        self._override_callback = callback
        
    def start(self) -> None:
        """Start the BACnet/SC hub in a background thread."""
        import asyncio
        
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        logger.info(f"BACnet/SC Hub starting on wss://{self._host}:{self._port}/bacnet-sc")
    
    def _run_server(self):
        """Run the WebSocket server in its own event loop."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._serve())
    
    async def _serve(self):
        """Main WebSocket server coroutine."""
        try:
            import websockets
            import ssl
            import json
            
            # Create SSL context for secure connections
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            
            # Generate self-signed cert for the hub (in production, use real certs)
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend
            from datetime import datetime, timedelta
            import tempfile
            import os
            
            # Generate hub certificate
            hub_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            hub_name = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BASim"),
                x509.NameAttribute(NameOID.COMMON_NAME, "BASim BACnet/SC Hub"),
            ])
            
            hub_cert = (
                x509.CertificateBuilder()
                .subject_name(hub_name)
                .issuer_name(hub_name)
                .public_key(hub_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.utcnow())
                .not_valid_after(datetime.utcnow() + timedelta(days=365))
                .add_extension(
                    x509.BasicConstraints(ca=True, path_length=None),
                    critical=True,
                )
                .sign(hub_key, hashes.SHA256(), default_backend())
            )
            
            # Write temp cert files
            cert_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False)
            cert_file.write(hub_cert.public_bytes(serialization.Encoding.PEM))
            cert_file.close()
            
            key_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False)
            key_file.write(hub_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
            key_file.close()
            
            ssl_context.load_cert_chain(cert_file.name, key_file.name)
            
            self._running = True
            
            async def handle_client(websocket):
                """Handle a BACnet/SC client connection."""
                client_id = f"client-{id(websocket)}"
                self._clients[client_id] = websocket
                logger.info(f"BACnet/SC client connected: {client_id} from {websocket.remote_address}")
                
                try:
                    async for message in websocket:
                        await self._handle_message(client_id, websocket, message)
                        
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"BACnet/SC client disconnected: {client_id}")
                finally:
                    if client_id in self._clients:
                        del self._clients[client_id]
            
            # Start WebSocket server
            self._server = await websockets.serve(
                handle_client,
                self._host,
                self._port,
                ssl=ssl_context,
                subprotocols=['bacnet-sc']
            )
            
            logger.info(f"BACnet/SC Hub running on wss://{self._host}:{self._port}")
            
            # Keep running
            await self._server.wait_closed()
            
            # Cleanup temp files
            os.unlink(cert_file.name)
            os.unlink(key_file.name)
            
        except ImportError:
            logger.warning("websockets library not installed - BACnet/SC hub disabled")
        except Exception as e:
            logger.error(f"BACnet/SC Hub error: {e}")
    
    async def _handle_message(self, client_id: str, websocket, message):
        """Handle incoming BACnet/SC message (Binary)."""
        import struct
        import uuid
        
        # Hub Constants
        HUB_VMAC = b'\x00\x00\x00\x00\x00\x01'
        HUB_UUID = uuid.UUID('ba51m000-0000-0000-0000-000000000001').bytes
        
        try:
            if not isinstance(message, bytes):
                logger.warning(f"Received non-binary message from {client_id}")
                return

            bvlc_function = message[0]
            
            if bvlc_function == 0x04: # Connect-Request
                # Payload: VMAC(6), UUID(16), MaxBVLC(2), MaxNPDU(2)
                if len(message) < 27:
                    return
                
                vmac, client_uuid, max_bvlc, max_npdu = struct.unpack('!6s16sHH', message[1:27])
                
                # Register device
                self._devices[client_id] = {
                    'vmac': vmac,
                    'uuid': client_uuid,
                    'connected_at': datetime.now().isoformat()
                }
                
                # Send Connect-Accept (0x05)
                # Payload: VMAC(6), UUID(16), MaxBVLC(2), MaxNPDU(2)
                response = struct.pack('!B6s16sHH', 
                    0x05, 
                    HUB_VMAC, 
                    HUB_UUID, 
                    1497, 
                    1497
                )
                await websocket.send(response)
                logger.info(f"BACnet/SC Connect-Accept sent to {client_id}")
                
            elif bvlc_function == 0x08: # Heartbeat-Request
                # Send Heartbeat-ACK (0x09)
                await websocket.send(b'\x09')
                
            elif bvlc_function == 0x02: # Encapsulated-NPDU
                # Payload: DestVMAC(6), SrcVMAC(6), MsgID(2), NPDU(...)
                if len(message) < 15:
                    return
                    
                dest_vmac, src_vmac, msg_id = struct.unpack('!6s6sH', message[1:15])
                npdu_data = message[15:]
                
                # Check if broadcast (DestVMAC = Broadcast VMAC usually FF:FF:FF:FF:FF:FF or similar, 
                # but in SC, broadcast is often handled via specific routing or just checking if it's for us)
                # For simplicity, we process everything as if it might be for us.
                
                # Parse NPDU
                # Version (1), Control (1)
                if len(npdu_data) < 2:
                    return
                    
                npdu_ver = npdu_data[0]
                npdu_ctrl = npdu_data[1]
                
                offset = 2
                
                # Destination Present?
                if npdu_ctrl & 0x20:
                    dnet_len = 0
                    # DNET (2), DLEN (1), DADR (DLEN), Hop (1)
                    # Wait, standard NPDU:
                    # DNET (2), DLEN (1), DADR...
                    offset += 2 # DNET
                    dlen = npdu_data[offset]
                    offset += 1 + dlen
                    offset += 1 # Hop Count
                
                # Source Present?
                if npdu_ctrl & 0x08:
                    offset += 2 # SNET
                    slen = npdu_data[offset]
                    offset += 1 + slen
                    # Hop count is only present once if Dest is present? 
                    # Actually Hop Count is after DADR if Dest is present.
                
                # APDU starts here
                if offset >= len(npdu_data):
                    return
                    
                apdu = npdu_data[offset:]
                apdu_type = (apdu[0] & 0xF0) >> 4
                
                if apdu_type == 0x01: # Unconfirmed-Request
                    service_choice = apdu[1]
                    if service_choice == 0x08: # Who-Is
                        logger.info("Received Who-Is via BACnet/SC")
                        # Send I-Am
                        # I-Am: Unconfirmed-Request(0x10), Service(0x00)
                        # Payload: ObjectIdentifier(Device, 9999), MaxAPDULen(1476), Segmentation(0), VendorID(15)
                        
                        # Construct I-Am APDU
                        # Type=1 (Unconfirmed), Service=0 (I-Am)
                        # Tags are application tagged.
                        # ObjID: Tag 12 (ObjectIdentifier) -> 4 bytes
                        # MaxAPDU: Tag 4 (Unsigned) -> 2 bytes?
                        # Segmentation: Tag 9 (Enum) -> 1 byte
                        # VendorID: Tag 2 (Unsigned) -> 1-2 bytes
                        
                        # Simplified manual encoding for I-Am
                        # 10 00 (Unconfirmed, I-Am)
                        # C4 02 00 27 0F (Object ID: Device 9999) -> Tag 12 (C=Class, 4=Len)
                        # 22 05 C4 (Max APDU: 1476) -> Tag 2 (Unsigned)
                        # 91 03 (Segmentation: Segmented Both) -> Tag 9 (Enum)
                        # 21 0F (Vendor ID: 15) -> Tag 2 (Unsigned)
                        
                        i_am_apdu = b'\x10\x00' + \
                                    b'\xC4\x02\x00\x27\x0F' + \
                                    b'\x22\x05\xC4' + \
                                    b'\x91\x03' + \
                                    b'\x21\x0F'
                        
                        # Wrap in NPDU
                        # Version 1, Control 0 (No src/dest)
                        resp_npdu = b'\x01\x00' + i_am_apdu
                        
                        # Wrap in Encapsulated-NPDU
                        # Dest=Src of request, Src=Hub
                        resp_bvlc = struct.pack('!B6s6sH', 0x02, src_vmac, HUB_VMAC, msg_id) + resp_npdu
                        await websocket.send(resp_bvlc)
                        
                elif apdu_type == 0x00: # Confirmed-Request
                    pdu_flags = apdu[0] & 0x0F
                    invoke_id = apdu[2]
                    service_choice = apdu[3]
                    
                    if service_choice == 0x0C: # ReadProperty
                        # Decode Object ID and Property ID
                        # Skip header (4 bytes)
                        rp_offset = 4
                        
                        # Object ID (Tag 0)
                        if apdu[rp_offset] == 0x0C:
                            obj_type = (apdu[rp_offset+1] >> 6) & 0x03 # High 10 bits (simplified)
                            # Actually Object Type is 10 bits.
                            # Byte 1: TTTT TTTT (Tag Number) -> 0000 1100 (Context 0, Len 4)
                            # Byte 2: TTTT TTTT (Type High 10) -> No, it's 4 bytes of data.
                            # Data: TTTT TTTT IIII IIII IIII IIII IIII IIII
                            # Type is 10 bits, Instance is 22 bits.
                            
                            # Let's unpack the 4 bytes of data
                            packed_oid = struct.unpack('!I', apdu[rp_offset+1:rp_offset+5])[0]
                            obj_type = (packed_oid >> 22) & 0x3FF
                            obj_inst = packed_oid & 0x3FFFFF
                            
                            rp_offset += 5
                            
                            # Property ID (Tag 1)
                            if apdu[rp_offset] == 0x19:
                                prop_id = apdu[rp_offset+1]
                                
                                value_tag = b''
                                
                                if prop_id == 77: # Object Name
                                    name = b'Unknown'
                                    if obj_type == 8: # Device
                                        name = b'CampusGateway'
                                    elif obj_inst < len(self._point_map):
                                        name = self._point_map[obj_inst]['name'].encode('utf-8')
                                    
                                    value_tag = b'\x75' + bytes([len(name)+1]) + b'\x00' + name
                                    
                                elif prop_id == 85: # Present Value
                                    val = 0.0
                                    if obj_inst < len(self._point_map):
                                        path = self._point_map[obj_inst]['path']
                                        val = self._read_point_value(path)
                                    
                                    # Encode Real (Tag 4)
                                    # Application Tag 4 = 0x44 (Class=0, Tag=4, Len=4)
                                    value_tag = b'\x44' + struct.pack('!f', val)
                                
                                # Construct Complex-ACK
                                ack_header = bytes([0x30, invoke_id, 0x0C])
                                obj_id_bytes = apdu[4:9]
                                prop_id_bytes = apdu[9:11]
                                value_part = b'\x3E' + value_tag + b'\x3F'
                                
                                ack_apdu = ack_header + obj_id_bytes + prop_id_bytes + value_part
                                resp_npdu = b'\x01\x00' + ack_apdu
                                resp_bvlc = struct.pack('!B6s6sH', 0x02, src_vmac, HUB_VMAC, msg_id) + resp_npdu
                                await websocket.send(resp_bvlc)
                    
                    elif service_choice == 0x0F: # WriteProperty
                        # Decode Object ID, Property ID, Value, Priority
                        wp_offset = 4
                        
                        # Object ID (Context 0)
                        if apdu[wp_offset] == 0x0C:
                            packed_oid = struct.unpack('!I', apdu[wp_offset+1:wp_offset+5])[0]
                            obj_inst = packed_oid & 0x3FFFFF
                            wp_offset += 5
                            
                            # Property ID (Context 1)
                            if apdu[wp_offset] == 0x19:
                                prop_id = apdu[wp_offset+1]
                                wp_offset += 2
                                
                                # Optional Property Index (Context 2) - Skip if present
                                if apdu[wp_offset] == 0x29: # Context 2, Len 1
                                    wp_offset += 2
                                
                                # Value (Context 3) - Opening Tag 3E
                                if apdu[wp_offset] == 0x3E:
                                    wp_offset += 1
                                    
                                    # Value Data - Assuming Real (Tag 4) or Boolean (Tag 9) or Null (Tag 0)
                                    # Simplified: Look for Real (0x44)
                                    val = 0.0
                                    if apdu[wp_offset] == 0x44:
                                        val = struct.unpack('!f', apdu[wp_offset+1:wp_offset+5])[0]
                                        wp_offset += 5
                                    
                                    # Skip to Closing Tag 3F
                                    while wp_offset < len(apdu) and apdu[wp_offset] != 0x3F:
                                        wp_offset += 1
                                    wp_offset += 1
                                    
                                    # Priority (Context 4) - Optional
                                    priority = 16
                                    if wp_offset < len(apdu) and apdu[wp_offset] == 0x49: # Context 4, Len 1
                                        priority = apdu[wp_offset+1]
                                    
                                    # Perform Write
                                    if prop_id == 85: # Present Value
                                        if obj_inst < len(self._point_map):
                                            path = self._point_map[obj_inst]['path']
                                            self._write_point_value(path, val, priority)
                                    
                                    # Send SimpleACK
                                    # PDU Type 2 (SimpleACK)
                                    # Invoke ID
                                    # Service Choice (15)
                                    ack_apdu = bytes([0x20, invoke_id, 0x0F])
                                    
                                    resp_npdu = b'\x01\x00' + ack_apdu
                                    resp_bvlc = struct.pack('!B6s6sH', 0x02, src_vmac, HUB_VMAC, msg_id) + resp_npdu
                                    await websocket.send(resp_bvlc)

            else:
                logger.debug(f"Unknown BACnet/SC BVLC Function: {bvlc_function}")
                
        except Exception as e:
            logger.error(f"Error handling BACnet/SC message: {e}")

    
    def _read_point_value(self, object_id: str) -> float:
        """Read a point value from the engine."""
        if not self._engine:
            return 0.0
        
        eng = self._engine
        
        # Parse object_id - could be "AI:1", "campus/oat", or path like "central_plant/chiller_1/status"
        obj_lower = object_id.lower()
        
        # Campus level
        if 'oat' in obj_lower or object_id == 'AI:1':
            return eng.oat
        
        # Electrical
        if 'main_meter_kw' in obj_lower or 'electrical' in obj_lower:
            if eng.electrical_system:
                if 'kwh' in obj_lower:
                    return eng.electrical_system.total_energy_kwh
                elif 'solar' in obj_lower:
                    return getattr(eng.electrical_system, 'solar_production_kw', 0.0)
                else:
                    return eng.electrical_system.total_demand_kw
        
        # Central plant
        if 'chiller' in obj_lower and eng.central_plant:
            # Extract chiller ID if present
            parts = object_id.split('/')
            for ch in eng.central_plant.chillers:
                if f'chiller_{ch.id}' in obj_lower:
                    if 'status' in obj_lower:
                        return float(ch.status)
                    elif 'chw_supply' in obj_lower:
                        return ch.chw_supply_temp
                    elif 'chw_return' in obj_lower:
                        return ch.chw_return_temp
                    elif 'load' in obj_lower:
                        return ch.load_percent
                    elif 'kw' in obj_lower:
                        return ch.kw
            # Default to first chiller
            if eng.central_plant.chillers:
                return eng.central_plant.chillers[0].chw_supply_temp
        
        if 'boiler' in obj_lower and eng.central_plant:
            for b in eng.central_plant.boilers:
                if f'boiler_{b.id}' in obj_lower:
                    if 'status' in obj_lower:
                        return float(b.status)
                    elif 'hw_supply' in obj_lower:
                        return b.hw_supply_temp
                    elif 'hw_return' in obj_lower:
                        return b.hw_return_temp
                    elif 'firing' in obj_lower:
                        return b.firing_rate
            if eng.central_plant.boilers:
                return eng.central_plant.boilers[0].hw_supply_temp
        
        # Building/AHU/VAV
        for bldg in eng.buildings:
            if f'building_{bldg.id}' in obj_lower or bldg.name.lower() in obj_lower:
                for ahu in bldg.ahus:
                    if f'ahu_{ahu.id}' in obj_lower or ahu.name.lower() in obj_lower:
                        if 'supply_temp' in obj_lower and 'setpoint' not in obj_lower:
                            return ahu.supply_temp
                        elif 'return_temp' in obj_lower:
                            return ahu.return_temp
                        elif 'supply_temp_setpoint' in obj_lower or 'supply_sp' in obj_lower:
                            return ahu.supply_temp_setpoint
                        elif 'fan_speed' in obj_lower or 'fan_cmd' in obj_lower:
                            return ahu.fan_speed
                        elif 'fan_status' in obj_lower:
                            return float(ahu.fan_status)
                        elif 'oa_damper' in obj_lower:
                            return ahu.outside_air_damper
                        
                        for vav in ahu.vavs:
                            if f'vav_{vav.id}' in obj_lower or vav.name.lower() in obj_lower:
                                if 'room_temp' in obj_lower:
                                    return vav.room_temp
                                elif 'cooling_setpoint' in obj_lower or 'cooling_sp' in obj_lower:
                                    return vav.cooling_setpoint
                                elif 'heating_setpoint' in obj_lower or 'heating_sp' in obj_lower:
                                    return vav.heating_setpoint
                                elif 'damper' in obj_lower:
                                    return vav.damper_position
                                elif 'airflow' in obj_lower:
                                    return vav.airflow_cfm
                                elif 'occupied' in obj_lower:
                                    return float(vav.occupied)
        
        # Data center
        if 'datacenter' in obj_lower or 'data_center' in obj_lower:
            dc = eng.data_center
            if dc and dc.enabled:
                if 'pue' in obj_lower:
                    return dc.pue
                elif 'load' in obj_lower or 'kw' in obj_lower:
                    return dc.total_it_load_kw
                
                for crac in dc.crac_units:
                    if f'crac_{crac.id}' in obj_lower:
                        if 'supply' in obj_lower:
                            return crac.supply_air_temp
                        elif 'return' in obj_lower:
                            return crac.return_air_temp
                        elif 'fan' in obj_lower:
                            return crac.fan_speed_pct
        
        # Wastewater
        if 'wastewater' in obj_lower:
            ww = eng.wastewater_facility
            if ww and ww.enabled:
                if 'influent' in obj_lower:
                    return ww.influent_flow_mgd
                elif 'effluent' in obj_lower:
                    return ww.effluent_flow_mgd
                elif 'do' in obj_lower or 'dissolved' in obj_lower:
                    return ww.dissolved_oxygen_mg_l
        
        return 0.0
    
    def _write_point_value(self, object_id: str, value: float, priority: int = 8) -> bool:
        """Write a value to a point (applies override)."""
        if not self._override_callback:
            logger.warning("No override callback configured for BACnet/SC writes")
            return False
        
        # Convert object_id to point path
        point_path = object_id.replace('/', '.')
        
        try:
            self._override_callback(point_path, value, priority)
            logger.info(f"BACnet/SC write: {object_id} = {value} @ priority {priority}")
            return True
        except Exception as e:
            logger.error(f"BACnet/SC write error: {e}")
            return False
    
    def _get_all_points(self) -> list:
        """Get list of all available points."""
        points = []
        
        if not self._engine:
            return points
        
        eng = self._engine
        
        # Campus
        points.append({'path': 'campus/oat', 'name': 'Outside Air Temperature', 'writable': False})
        
        # Buildings
        for bldg in eng.buildings:
            for ahu in bldg.ahus:
                prefix = f'building_{bldg.id}/ahu_{ahu.id}'
                points.extend([
                    {'path': f'{prefix}/supply_temp', 'name': f'{bldg.name} {ahu.name} Supply Temp', 'writable': False},
                    {'path': f'{prefix}/supply_temp_setpoint', 'name': f'{bldg.name} {ahu.name} Supply SP', 'writable': True},
                    {'path': f'{prefix}/fan_speed', 'name': f'{bldg.name} {ahu.name} Fan Speed', 'writable': True},
                    {'path': f'{prefix}/enable', 'name': f'{bldg.name} {ahu.name} Enable', 'writable': True},
                ])
                
                for vav in ahu.vavs:
                    vav_prefix = f'{prefix}/vav_{vav.id}'
                    points.extend([
                        {'path': f'{vav_prefix}/room_temp', 'name': f'{vav.zone_name} Room Temp', 'writable': False},
                        {'path': f'{vav_prefix}/cooling_setpoint', 'name': f'{vav.zone_name} Cooling SP', 'writable': True},
                        {'path': f'{vav_prefix}/damper', 'name': f'{vav.zone_name} Damper', 'writable': True},
                    ])
        
        # Central plant
        if eng.central_plant:
            for ch in eng.central_plant.chillers:
                prefix = f'central_plant/chiller_{ch.id}'
                points.extend([
                    {'path': f'{prefix}/status', 'name': f'Chiller {ch.id} Status', 'writable': False},
                    {'path': f'{prefix}/enable', 'name': f'Chiller {ch.id} Enable', 'writable': True},
                    {'path': f'{prefix}/chw_supply_temp', 'name': f'Chiller {ch.id} CHW Supply', 'writable': False},
                    {'path': f'{prefix}/load_percent', 'name': f'Chiller {ch.id} Load %', 'writable': False},
                ])
        
        # Electrical
        if eng.electrical_system:
            points.extend([
                {'path': 'electrical/main_meter_kw', 'name': 'Main Meter kW', 'writable': False},
                {'path': 'electrical/main_meter_kwh', 'name': 'Main Meter kWh', 'writable': False},
            ])
        
        return points
    
    def stop(self) -> None:
        """Stop the BACnet/SC hub."""
        self._running = False
        if self._server:
            self._server.close()
        logger.info("BACnet/SC Hub stopped")
    
    def register_point(self, name: str, initial_value: float = 0.0, writable: bool = False) -> None:
        """Register a point (not used for SC hub)."""
        pass
    
    def update_point(self, name: str, value: float) -> None:
        """Update a point value."""
        pass
    
    def get_point(self, name: str) -> float:
        """Get a point value."""
        return 0.0
    
    @property
    def connected_clients(self) -> int:
        """Return number of connected clients."""
        return len(self._clients)
    
    @property
    def registered_devices(self) -> int:
        """Return number of registered devices."""
        return len(self._devices)
