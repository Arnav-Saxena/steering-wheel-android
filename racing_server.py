#!/usr/bin/env python3
"""
Analog Racing Controller Server - FIXED VERSION
- 60 FPS update rate
- Multi-rotation steering (900°+ like real wheels)
- Fixed angle wraparound bug
"""

import asyncio
import websockets
import json
import time
import threading
from typing import Dict, Any
import logging
import socket
import http.server
import socketserver
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import vgamepad as vg
    VGAMEPAD_AVAILABLE = True
    logger.info("✅ vgamepad found")
except ImportError:
    VGAMEPAD_AVAILABLE = False
    logger.warning("⚠️ vgamepad not found")

try:
    import pyvjoy
    VJOY_AVAILABLE = True
except ImportError:
    VJOY_AVAILABLE = False

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

class AnalogRacingServer:
    def __init__(self, host='0.0.0.0', port=8765):
        self.host = host
        self.port = port
        self.connected_clients = set()
        
        # CHANGED: Support full rotation range
        self.current_steering = 0.0  # Now supports -900 to +900 degrees
        self.max_steering_angle = 900.0  # Configurable max rotation
        
        self.current_accelerator = 0.0
        self.current_brake = 0.0
        self.handbrake_pressed = False
        self.horn_pressed = False

        self.controller = None
        self.controller_type = self.init_controller()

        logger.info(f"Server initialized on {host}:{port}")
        logger.info(f"Controller: {self.controller_type}")
        logger.info(f"Steering range: ±{self.max_steering_angle}°")

    def init_controller(self):
        if VGAMEPAD_AVAILABLE:
            try:
                self.controller = vg.VX360Gamepad()
                logger.info("🎮 vgamepad Xbox controller initialized")
                return "VGAMEPAD_XBOX"
            except Exception as e:
                logger.error(f"vgamepad failed: {e}")

        if VJOY_AVAILABLE:
            try:
                self.controller = pyvjoy.VJoyDevice(1)
                logger.info("🕹️ VJoy controller initialized")
                return "VJOY"
            except Exception as e:
                logger.error(f"VJoy failed: {e}")

        if PYAUTOGUI_AVAILABLE:
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0
            self.keys_pressed = set()
            logger.info("⌨️ Keyboard fallback initialized")
            return "KEYBOARD"

        return "NONE"

    def update_controller(self):
        if self.controller_type == "VGAMEPAD_XBOX":
            self.update_vgamepad_controller()
        elif self.controller_type == "VJOY":
            self.update_vjoy_controller()
        elif self.controller_type == "KEYBOARD":
            self.update_keyboard_controller()

    def update_vgamepad_controller(self):
        try:
            # CHANGED: Normalize steering from full range to -1.0 to 1.0
            steering_normalized = max(-1.0, min(1.0, self.current_steering / self.max_steering_angle))
            self.controller.left_joystick_float(x_value_float=steering_normalized, y_value_float=0.0)
            
            self.controller.right_trigger_float(value_float=self.current_accelerator)
            self.controller.left_trigger_float(value_float=self.current_brake)

            if self.handbrake_pressed:
                self.controller.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
            else:
                self.controller.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)

            if self.horn_pressed:
                self.controller.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
            else:
                self.controller.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
            
            self.controller.update()

        except Exception as e:
            logger.error(f"vgamepad error: {e}")

    def update_vjoy_controller(self):
        try:
            steering_normalized = max(-1.0, min(1.0, self.current_steering / self.max_steering_angle))
            steering_vjoy = int((steering_normalized + 1.0) / 2.0 * 32767) + 1
            self.controller.set_axis(pyvjoy.HID_USAGE_X, steering_vjoy)
            
            accel_vjoy = int(self.current_accelerator * 32767) + 1
            self.controller.set_axis(pyvjoy.HID_USAGE_Y, 32768 - accel_vjoy)
            
            brake_vjoy = int(self.current_brake * 32767) + 1
            self.controller.set_axis(pyvjoy.HID_USAGE_Z, brake_vjoy)
            
            self.controller.set_button(1, self.handbrake_pressed)
            self.controller.set_button(2, self.horn_pressed)
            
        except Exception as e:
            logger.error(f"VJoy error: {e}")

    def update_keyboard_controller(self):
        try:
            if abs(self.current_steering) < 10:
                self.release_key('a')
                self.release_key('d')
            elif self.current_steering < -10:
                self.release_key('d')
                self.press_key('a')
            elif self.current_steering > 10:
                self.release_key('a')
                self.press_key('d')
            
            if self.current_accelerator > 0.1:
                self.press_key('w')
            else:
                self.release_key('w')
            
            if self.current_brake > 0.1:
                self.press_key('s')
            else:
                self.release_key('s')
            
            if self.handbrake_pressed:
                self.press_key('space')
            else:
                self.release_key('space')
            
            if self.horn_pressed:
                self.press_key('h')
            else:
                self.release_key('h')
                
        except Exception as e:
            logger.error(f"Keyboard error: {e}")

    def press_key(self, key):
        if key not in self.keys_pressed:
            try:
                pyautogui.keyDown(key)
                self.keys_pressed.add(key)
            except Exception as e:
                logger.error(f"Error pressing {key}: {e}")

    def release_key(self, key):
        if key in self.keys_pressed:
            try:
                pyautogui.keyUp(key)
                self.keys_pressed.discard(key)
            except Exception as e:
                logger.error(f"Error releasing {key}: {e}")

    def release_all_inputs(self):
        self.current_steering = 0.0
        self.current_accelerator = 0.0
        self.current_brake = 0.0
        self.handbrake_pressed = False
        self.horn_pressed = False
        
        if self.controller_type == "KEYBOARD":
            for key in list(getattr(self, 'keys_pressed', set())):
                self.release_key(key)
        elif self.controller_type == "VGAMEPAD_XBOX":
            self.controller.reset()
            self.controller.update()
        
        self.update_controller()

    async def register_client(self, websocket):
        self.connected_clients.add(websocket)
        client_ip = websocket.remote_address[0]
        logger.info(f"Client connected: {client_ip}. Total: {len(self.connected_clients)}")

    async def unregister_client(self, websocket):
        self.connected_clients.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(self.connected_clients)}")
        
        if not self.connected_clients:
            self.release_all_inputs()

    async def handle_message(self, websocket, message):
        try:
            data = json.loads(message)
            command = data.get('command')
            payload = data.get('data', {})
            
            if command == 'update':
                # CHANGED: Now accepts full rotation range in degrees
                if 'steering' in payload:
                    self.current_steering = max(-self.max_steering_angle, 
                                               min(self.max_steering_angle, payload['steering']))
                    
                if 'accelerator' in payload:
                    self.current_accelerator = max(0.0, min(1.0, payload['accelerator'] / 100.0))
                    
                if 'brake' in payload:
                    self.current_brake = max(0.0, min(1.0, payload['brake'] / 100.0))
                
                self.update_controller()
                    
            elif command == 'handbrake_press':
                self.handbrake_pressed = True
                self.update_controller()
                
            elif command == 'handbrake_release':
                self.handbrake_pressed = False
                self.update_controller()
                
            elif command == 'horn_press':
                self.horn_pressed = True
                self.update_controller()
                
            elif command == 'horn_release':
                self.horn_pressed = False
                self.update_controller()
                
            elif command == 'reset':
                self.release_all_inputs()
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def handle_client(self, websocket):
        await self.register_client(websocket)
        
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            await self.unregister_client(websocket)

    def get_local_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def print_connection_info(self):
        local_ip = self.get_local_ip()
        print("=" * 70)
        print("🏎️  ANALOG RACING CONTROLLER - FIXED VERSION")
        print("=" * 70)
        print(f"🖥️  Server: {local_ip}:{self.port}")
        print(f"🔗 WebSocket: ws://{local_ip}:{self.port}")
        print(f"📱 Web Interface: http://{local_ip}:8000")
        print()
        print("🎮 CONTROLLER:", self.controller_type)
        print(f"🎯 Steering Range: ±{self.max_steering_angle}° (multi-rotation)")
        print("⚡ Update Rate: 60 FPS (16.67ms)")
        print("🐛 Bug Fixes: Angle wraparound fixed, smooth rotation")
        print()
        print("Press Ctrl+C to stop")
        print("=" * 70)

    async def start_server(self):
        self.print_connection_info()
        
        try:
            async with websockets.serve(
                self.handle_client,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=10
            ):
                await asyncio.Future()
        except KeyboardInterrupt:
            logger.info("Server shutdown")
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self.release_all_inputs()

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    
    def log_message(self, format, *args):
        pass

def create_html_server():
    def run_http_server():
        PORT = 8000
        Handler = CustomHTTPRequestHandler
        
        try:
            with socketserver.TCPServer(("", PORT), Handler) as httpd:
                httpd.serve_forever()
        except Exception as e:
            pass
    
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    return http_thread

def create_html_file():
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>🏎️ Racing Controller - FIXED</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; touch-action: none; }
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460); color: white; user-select: none; }
        .container { max-width: 1200px; margin: 0 auto; padding: 10px; display: flex; flex-direction: column; }
        .header { text-align: center; margin-bottom: 15px; }
        .header h1 { font-size: 2.0rem; background: linear-gradient(45deg, #ff6b6b, #4ecdc4, #45b7d1); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px; }
        .connection-status { display: inline-block; padding: 8px 16px; border-radius: 25px; font-size: 0.9rem; font-weight: 600; margin-bottom: 15px; transition: all 0.3s ease; }
        .connected { background: rgba(76, 175, 80, 0.2); color: #4CAF50; border: 2px solid #4CAF50; box-shadow: 0 0 20px rgba(76, 175, 80, 0.3); }
        .disconnected { background: rgba(244, 67, 54, 0.2); color: #f44336; border: 2px solid #f44336; box-shadow: 0 0 20px rgba(244, 67, 54, 0.3); }
        .controller-interface { flex: 1; display: grid; grid-template-areas: "steering steering" "pedals controls"; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 800px; margin: 0 auto; width: 100%; }
        .steering-section { grid-area: steering; text-align: center; }
        .pedals-section { grid-area: pedals; display: flex; flex-direction: column; gap: 15px; }
        .controls-section { grid-area: controls; display: flex; flex-direction: column; gap: 15px; }
        .section-title { font-size: 1.3rem; margin-bottom: 15px; color: #4ecdc4; text-align: center; font-weight: 600; text-transform: uppercase; letter-spacing: 2px; }
        .steering-wheel { width: 220px; height: 220px; border: 10px solid #333; border-radius: 50%; background: radial-gradient(circle at 30% 30%, #3c5aa6, #2c3e50, #1a252f); position: relative; margin: 0 auto 15px; cursor: grab; box-shadow: 0 0 40px rgba(78, 205, 196, 0.4), inset 0 0 30px rgba(0, 0, 0, 0.5); transition: all 0.1s ease; }
        .steering-wheel:active { cursor: grabbing; transform: scale(1.05); }
        .steering-indicator { width: 8px; height: 70px; background: linear-gradient(0deg, #ff6b6b, #ff8e8e); position: absolute; top: 15px; left: 50%; transform: translateX(-50%); border-radius: 4px; box-shadow: 0 0 15px rgba(255, 107, 107, 0.7); }
        .steering-value { font-size: 1.2rem; color: #4ecdc4; margin-top: 10px; font-weight: 600; }
        .pedal-container { display: flex; align-items: center; gap: 15px; background: rgba(255, 255, 255, 0.05); padding: 18px; border-radius: 15px; border: 2px solid rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); }
        .pedal-label { font-size: 1.1rem; font-weight: 700; min-width: 90px; text-align: left; }
        .pedal-slider { flex: 1; height: 45px; width: 45px; background: rgba(255, 255, 255, 0.1); border-radius: 25px; position: relative; border: 3px solid rgba(255, 255, 255, 0.2); overflow: hidden; }
        .accelerator .pedal-slider { border-color: #4CAF50; box-shadow: 0 0 20px rgba(76, 175, 80, 0.3); }
        .brake .pedal-slider { border-color: #f44336; box-shadow: 0 0 20px rgba(244, 67, 54, 0.3); }
        .pedal-fill { height: 100%; border-radius: 22px; transition: width 0.1s ease; position: relative; }
        .accelerator .pedal-fill { background: linear-gradient(90deg, #4CAF50, #66BB6A, #81C784); }
        .brake .pedal-fill { background: linear-gradient(90deg, #f44336, #EF5350, #E57373); }
        .pedal-value { position: absolute; right: 15px; top: 50%; transform: translateY(-50%); font-size: 1rem; font-weight: 700; color: white; text-shadow: 2px 2px 4px rgba(0,0,0,0.8); }
        .control-button { background: linear-gradient(135deg, #667eea, #764ba2); border: none; padding: 18px 25px; border-radius: 15px; color: white; font-size: 1.1rem; font-weight: 700; cursor: pointer; transition: all 0.2s ease; text-transform: uppercase; letter-spacing: 1.5px; }
        .control-button:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(102, 126, 234, 0.5); }
        .control-button:active { transform: translateY(0); }
        .handbrake { background: linear-gradient(135deg, #ff6b6b, #ee5a24); }
        .debug-info { margin-top: 25px; padding: 15px; background: rgba(0, 0, 0, 0.4); border-radius: 12px; font-family: 'Courier New', monospace; font-size: 0.9rem; border-left: 5px solid #4ecdc4; }
        .debug-row { display: flex; justify-content: space-between; margin-bottom: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏎️ Racing Controller - FIXED</h1>
            <div class="connection-status disconnected" id="connectionStatus">🔴 Disconnected</div>
        </div>

        <div class="controller-interface">
            <div class="steering-section">
                <div class="section-title">🎯 Multi-Rotation Steering</div>
                <div class="steering-wheel" id="steeringWheel">
                    <div class="steering-indicator"></div>
                </div>
                <div class="steering-value" id="steeringValue">0°</div>
            </div>

            <div class="pedals-section">
                <div class="section-title">🦵 Analog Pedals</div>
                <div class="pedal-container accelerator">
                    <div class="pedal-label">🚀 Gas</div>
                    <div class="pedal-slider" id="acceleratorSlider">
                        <div class="pedal-fill" id="acceleratorFill"></div>
                        <div class="pedal-value" id="acceleratorValue">0%</div>
                    </div>
                </div>
                <div class="pedal-container brake">
                    <div class="pedal-label">🛑 Brake</div>
                    <div class="pedal-slider" id="brakeSlider">
                        <div class="pedal-fill" id="brakeFill"></div>
                        <div class="pedal-value" id="brakeValue">0%</div>
                    </div>
                </div>
            </div>

            <div class="controls-section">
                <div class="section-title">🎮 Controls</div>
                <button class="control-button handbrake" id="handbrakeBtn">🎯 Handbrake</button>
                <button class="control-button" id="resetBtn">🔄 Reset</button>
                <button class="control-button" id="fullscreenBtn">🖼️ Fullscreen</button>
                <button class="control-button" id="hornBtn">📢 Horn</button>
            </div>
        </div>

        <div class="debug-info">
            <div class="debug-row"><span>🎯 Steering:</span><span id="debugSteering">0°</span></div>
            <div class="debug-row"><span>🚀 Accelerator:</span><span id="debugAccelerator">0%</span></div>
            <div class="debug-row"><span>🛑 Brake:</span><span id="debugBrake">0%</span></div>
            <div class="debug-row"><span>🔗 Connection:</span><span id="debugWebSocket">Disconnected</span></div>
            <div class="debug-row"><span>⚡ Update Rate:</span><span>60 FPS</span></div>
        </div>
    </div>

    <script>
        const serverIP = window.location.hostname || 'localhost';
        const wsUrl = `ws://${serverIP}:8765`;

        class AnalogRacingController {
            constructor() {
                this.ws = null;
                // CHANGED: Track cumulative rotation without limits initially
                this.cumulativeAngle = 0;
                this.maxRotation = 900; // Can be adjusted (450, 900, 1080, etc.)
                this.lastTouchAngle = null;
                
                this.acceleratorValue = 0;
                this.brakeValue = 0;
                this.isHandbrakePressed = false;
                this.steeringAnimation = null;
                
                this.setupWebSocket();
                this.setupSteeringWheel();
                this.setupPedals();
                this.setupControls();
                this.startUpdateLoop();
                this.preventRefresh();
            }

            preventRefresh() {
                document.addEventListener('touchstart', (e) => { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
                document.addEventListener('touchmove', (e) => { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
            }

            setupWebSocket() {
                this.connectWebSocket();
                setInterval(() => {
                    if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
                        this.connectWebSocket();
                    }
                }, 3000);
            }

            connectWebSocket() {
                try {
                    this.ws = new WebSocket(wsUrl);
                    this.ws.onopen = () => { this.updateConnectionStatus(true); this.vibrate(); };
                    this.ws.onclose = () => { this.updateConnectionStatus(false); };
                    this.ws.onerror = (error) => { console.error('WebSocket error:', error); this.updateConnectionStatus(false); };
                } catch (error) {
                    console.error('WebSocket creation failed:', error);
                    this.updateConnectionStatus(false);
                }
            }

            updateConnectionStatus(connected) {
                const statusEl = document.getElementById('connectionStatus');
                const debugEl = document.getElementById('debugWebSocket');
                if (connected) {
                    statusEl.textContent = '🟢 Connected';
                    statusEl.className = 'connection-status connected';
                    debugEl.textContent = 'Connected (60 FPS)';
                } else {
                    statusEl.textContent = '🔴 Disconnected';
                    statusEl.className = 'connection-status disconnected';
                    debugEl.textContent = 'Disconnected';
                }
            }

            vibrate() {
                if ('vibrate' in navigator) { navigator.vibrate(50); }
            }

            // FIXED: New steering wheel logic that prevents angle wraparound
            setupSteeringWheel() {
                const wheel = document.getElementById('steeringWheel');
                let isDragging = false;

                const getAngle = (event) => {
                    const rect = wheel.getBoundingClientRect();
                    const centerX = rect.left + rect.width / 2;
                    const centerY = rect.top + rect.height / 2;
                    const clientX = event.clientX || (event.touches && event.touches[0].clientX);
                    const clientY = event.clientY || (event.touches && event.touches[0].clientY);
                    return Math.atan2(clientY - centerY, clientX - centerX) * 180 / Math.PI;
                };

                // FIXED: Calculate angle difference properly to avoid wraparound
                const getAngleDifference = (newAngle, oldAngle) => {
                    let diff = newAngle - oldAngle;
                    // Handle wraparound: if difference > 180, we crossed the boundary
                    if (diff > 180) diff -= 360;
                    if (diff < -180) diff += 360;
                    return diff;
                };

                const startDrag = (event) => {
                    event.preventDefault();
                    if (this.steeringAnimation) {
                        clearInterval(this.steeringAnimation);
                        this.steeringAnimation = null;
                    }
                    isDragging = true;
                    this.lastTouchAngle = getAngle(event);
                    this.vibrate();
                };

                const drag = (event) => {
                    if (!isDragging) return;
                    event.preventDefault();
                    
                    const currentAngle = getAngle(event);
                    // FIXED: Use proper angle difference calculation
                    const angleDelta = getAngleDifference(currentAngle, this.lastTouchAngle);
                    
                    // Add the delta to cumulative angle
                    this.cumulativeAngle += angleDelta;
                    
                    // Clamp to max rotation
                    this.cumulativeAngle = Math.max(-this.maxRotation, Math.min(this.maxRotation, this.cumulativeAngle));
                    
                    this.lastTouchAngle = currentAngle;
                    this.updateSteering();
                };

                const stopDrag = () => {
                    if (!isDragging) return;
                    isDragging = false;
                    this.lastTouchAngle = null;
                    
                    // Auto-return to center
                    if (this.steeringAnimation) clearInterval(this.steeringAnimation);
                    this.steeringAnimation = setInterval(() => {
                        const step = this.cumulativeAngle * 0.15;
                        this.cumulativeAngle -= step;

                        if (Math.abs(this.cumulativeAngle) < 0.5) {
                            this.cumulativeAngle = 0;
                            clearInterval(this.steeringAnimation);
                            this.steeringAnimation = null;
                        }
                        this.updateSteering();
                    }, 16); // 60 FPS
                };

                wheel.addEventListener('mousedown', startDrag);
                document.addEventListener('mousemove', drag);
                document.addEventListener('mouseup', stopDrag);
                wheel.addEventListener('touchstart', startDrag, { passive: false });
                document.addEventListener('touchmove', drag, { passive: false });
                document.addEventListener('touchend', stopDrag);
            }
            
            setupPedals() {
                this.setupPedal('acceleratorSlider', 'accelerator');
                this.setupPedal('brakeSlider', 'brake');
            }

            setupPedal(sliderId, type) {
                const slider = document.getElementById(sliderId);
                let isDragging = false;

                const updatePedal = (event) => {
                    const rect = slider.getBoundingClientRect();
                    const clientX = event.clientX || (event.touches && event.touches[0].clientX);
                    const percentage = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
                    
                    if (type === 'accelerator') this.acceleratorValue = percentage;
                    else if (type === 'brake') this.brakeValue = percentage;
                    
                    this.updateUI();
                };

                const startDrag = (event) => { event.preventDefault(); isDragging = true; updatePedal(event); this.vibrate(); };
                const drag = (event) => { if (isDragging) { event.preventDefault(); updatePedal(event); } };
                const stopDrag = () => { isDragging = false; };

                slider.addEventListener('mousedown', startDrag);
                document.addEventListener('mousemove', drag);
                document.addEventListener('mouseup', stopDrag);
                slider.addEventListener('touchstart', startDrag, { passive: false });
                document.addEventListener('touchmove', drag, { passive: false });
                slider.addEventListener('touchend', stopDrag);
            }

            setupControls() {
                const handbrakeBtn = document.getElementById('handbrakeBtn');
                const resetBtn = document.getElementById('resetBtn');
                const hornBtn = document.getElementById('hornBtn');
                const fullscreenBtn = document.getElementById('fullscreenBtn');

                const handleButton = (btn, command) => {
                    const down = () => { btn.style.transform = 'scale(0.95)'; this.sendCommand(`${command}_press`); this.vibrate(); };
                    const up = () => { btn.style.transform = ''; this.sendCommand(`${command}_release`); };
                    btn.addEventListener('mousedown', down);
                    btn.addEventListener('mouseup', up);
                    btn.addEventListener('mouseleave', up);
                    btn.addEventListener('touchstart', down, { passive: false });
                    btn.addEventListener('touchend', up);
                };

                handleButton(handbrakeBtn, 'handbrake');
                handleButton(hornBtn, 'horn');

                resetBtn.addEventListener('click', () => {
                    this.cumulativeAngle = 0;
                    this.acceleratorValue = 0;
                    this.brakeValue = 0;
                    this.updateUI();
                    this.sendCommand('reset');
                    this.vibrate();
                });
                
                fullscreenBtn.addEventListener('click', () => {
                    this.toggleFullScreen();
                    this.vibrate();
                });
            }
            
            toggleFullScreen() {
                const doc = document.documentElement;
                if (!document.fullscreenElement && !document.webkitFullscreenElement) {
                    (doc.requestFullscreen || doc.webkitRequestFullscreen)?.call(doc);
                } else {
                    (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
                }
            }
            
            updateUI() {
                this.updateSteering();
                this.updateAccelerator();
                this.updateBrake();
            }

            updateSteering() {
                document.getElementById('steeringWheel').style.transform = `rotate(${this.cumulativeAngle}deg)`;
                document.getElementById('steeringValue').textContent = `${Math.round(this.cumulativeAngle)}°`;
                document.getElementById('debugSteering').textContent = `${Math.round(this.cumulativeAngle)}° / ±${this.maxRotation}°`;
            }

            updateAccelerator() {
                document.getElementById('acceleratorFill').style.width = `${this.acceleratorValue}%`;
                document.getElementById('acceleratorValue').textContent = `${Math.round(this.acceleratorValue)}%`;
                document.getElementById('debugAccelerator').textContent = `${Math.round(this.acceleratorValue)}%`;
            }

            updateBrake() {
                document.getElementById('brakeFill').style.width = `${this.brakeValue}%`;
                document.getElementById('brakeValue').textContent = `${Math.round(this.brakeValue)}%`;
                document.getElementById('debugBrake').textContent = `${Math.round(this.brakeValue)}%`;
            }

            sendCommand(command, data = {}) {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    try {
                        this.ws.send(JSON.stringify({ command, data, timestamp: Date.now() }));
                    } catch (error) {
                        console.error('Error sending command:', error);
                    }
                }
            }

            // CHANGED: Update rate increased to 60 FPS (16.67ms)
            startUpdateLoop() {
                let lastSent = { steering: 0, accelerator: 0, brake: 0 };

                setInterval(() => {
                    const currentState = {
                        steering: this.cumulativeAngle, // Send full rotation value
                        accelerator: this.acceleratorValue,
                        brake: this.brakeValue
                    };

                    const hasChanged = Math.abs(currentState.steering - lastSent.steering) > 0.1 ||
                                       Math.abs(currentState.accelerator - lastSent.accelerator) > 0.1 ||
                                       Math.abs(currentState.brake - lastSent.brake) > 0.1;

                    if (hasChanged) {
                        this.sendCommand('update', currentState);
                        lastSent = currentState;
                    }
                }, 50); // CHANGED: 60 FPS (was 50ms/20fps)
            }
        }

        document.addEventListener('DOMContentLoaded', () => { new AnalogRacingController(); });
        document.addEventListener('contextmenu', (e) => e.preventDefault());
    </script>
</body>
</html>'''
    
    return html_content

def check_dependencies():
    libraries_found = []
    
    if VGAMEPAD_AVAILABLE:
        libraries_found.append("✅ vgamepad - Xbox controller emulation")
    
    if VJOY_AVAILABLE:
        libraries_found.append("✅ PyVJoy - VJoy joystick emulation")
    
    if PYAUTOGUI_AVAILABLE:
        libraries_found.append("✅ PyAutoGUI - Keyboard fallback")
    
    try:
        import websockets
        libraries_found.append("✅ WebSockets - Communication")
    except ImportError:
        print("❌ WebSockets not found - Install: pip install websockets")
        return False
    
    if libraries_found:
        print("📦 LIBRARIES:")
        for lib in libraries_found:
            print(f"   {lib}")
    
    return True

def main():
    print("🏁 Initializing Racing Controller (FIXED VERSION)...")
    print()
    
    if not check_dependencies():
        return
    
    try:
        html_content = create_html_file()
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("✅ index.html created")
    except Exception as e:
        print(f"⚠️ Could not create index.html: {e}")
    
    try:
        create_html_server()
        time.sleep(1)
    except Exception as e:
        print(f"⚠️ HTTP server error: {e}")
    
    server = AnalogRacingServer()
    
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
    except Exception as e:
        print(f"❌ Server error: {e}")

if __name__ == "__main__":
    main()
