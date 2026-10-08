import time
import threading
import pygame
import atexit
import tkinter as tk
from tkinter import ttk
from pynput.keyboard import Key, KeyCode, Controller

# =============================================================================
# 🎛️ CONFIGURATION
# =============================================================================
AXIS_INDEX = 1
INVERT_AXIS = True   

MAX_STEPS = 30          
HOLD_DURATION = 0.04    
SHIFT_DELAY = 0.05      

# Set stability threshold to exactly 1/30th of full scale deflection (approx 0.033)
STABILITY_WINDOW = 1.0 / float(MAX_STEPS) 
# =============================================================================

KEY_W = KeyCode.from_char('w')
KEY_S = KeyCode.from_char('s')
KEY_SPACE = Key.space

# Initialize game input engine
pygame.init()
pygame.joystick.init()
pygame.event.pump()

# Target G27 Wheel/Pedal Set
g27_index = None
for i in range(pygame.joystick.get_count()):
    temp_joy = pygame.joystick.Joystick(i)
    temp_joy.init()
    if "G27" in temp_joy.get_name() or "Driving Force" in temp_joy.get_name():
        g27_index = i
        break

if g27_index is None:
    print("❌ Error: G27 not found among connected controllers.")
    wheel = None
else:
    wheel = pygame.joystick.Joystick(g27_index)
    wheel.init()

keyboard = Controller()
current_pct = 0.0  
running = True

# UI Shared State Variables
ui_status_text = "Initializing..."
ui_pedal_pct = 0

def EMERGENCY_RELEASE():
    try:
        keyboard.release(KEY_W)
        keyboard.release(KEY_S)
        keyboard.release(KEY_SPACE)
    except:
        pass

atexit.register(EMERGENCY_RELEASE)

def force_boot_zero():
    """Forces the game speed setting to absolute zero on startup by pinning S down."""
    global ui_status_text
    ui_status_text = "🔄 Synchronising Boot Baseline..."
    print("⏳ System Boot: Forcing slider to 0...")
    
    keyboard.press(KEY_S)
    time.sleep(1.2)
    keyboard.release(KEY_S)
    print("✨ Boot Baseline Secured.")

def core_execution_loop():
    global current_simulated_speed, target_speed, current_pct, running
    global ui_status_text, ui_pedal_pct
    
    force_boot_zero()
    
    current_simulated_speed = 0  
    target_speed = 0             
    space_is_held = False
    s_is_held_down = False      
    last_stable_pct = 0.0     
    
    if wheel is None:
        ui_status_text = "🔴 G27 Disconnected"
        return

    while running:
        pct = current_pct
        ui_pedal_pct = int(pct * 100)
        
        # ---------------------------------------------------------------------
        # STATE 1: SAFETY ABSOLUTE (0% Travel)
        # ---------------------------------------------------------------------
        if pct <= 0.01:
            if space_is_held:
                keyboard.release(KEY_SPACE)
                space_is_held = False
            if s_is_held_down:
                keyboard.release(KEY_S)
                s_is_held_down = False
            
            ui_status_text = "🟢 Idle / Standby"
            current_simulated_speed = 0
            target_speed = 0
            last_stable_pct = pct
            time.sleep(0.05)
            continue
            
        # ---------------------------------------------------------------------
        # STATE 2: CONTINUOUS S-HOLD DEADZONE (1% to 10% Pressed)
        # ---------------------------------------------------------------------
        elif 0.01 < pct <= 0.10:
            if space_is_held:
                keyboard.release(KEY_SPACE)
                space_is_held = False
                
            if not s_is_held_down:
                keyboard.press(KEY_S)
                s_is_held_down = True
            
            ui_status_text = "🔒 Clearing Baseline (Holding S)"
            current_simulated_speed = 0
            target_speed = 0
            last_stable_pct = pct
            time.sleep(0.02)
            continue

        # ---------------------------------------------------------------------
        # STATE 3 & 4: ACTIVE SEWING THROW (10% to 100% Pressed Travel)
        # ---------------------------------------------------------------------
        else:
            if s_is_held_down:
                keyboard.release(KEY_S)
                s_is_held_down = False

            if not space_is_held:
                keyboard.press(KEY_SPACE)
                space_is_held = True

            # Modified Stability Window: Strictly tied to 1/30th increments
            if abs(pct - last_stable_pct) <= STABILITY_WINDOW:
                ui_status_text = f"🧵 Sewing Steady (Speed {current_simulated_speed}/{MAX_STEPS})"
                time.sleep(0.02)
                continue
                
            scale_factor = (pct - 0.10) / (1.0 - 0.10)
            calculated_target = int(round(scale_factor * MAX_STEPS))
            target_speed = max(0, min(MAX_STEPS, calculated_target))
            
            ui_status_text = f"⚙️ Adjusting Speed ({current_simulated_speed} ➔ {target_speed})"
            
            if current_simulated_speed < target_speed:
                keyboard.press(KEY_W)
                time.sleep(HOLD_DURATION)
                keyboard.release(KEY_W)
                current_simulated_speed += 1
                time.sleep(SHIFT_DELAY)
            elif current_simulated_speed > target_speed:
                keyboard.press(KEY_S)
                time.sleep(HOLD_DURATION)
                keyboard.release(KEY_S)
                current_simulated_speed -= 1
                time.sleep(SHIFT_DELAY)
            else:
                last_stable_pct = pct
                time.sleep(0.01)

# --- GRAPHICAL USER INTERFACE ---
class SewingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("G27 Sewing Assistant")
        self.root.geometry("340x220")
        self.root.resizable(False, False)
        
        style = ttk.Style()
        style.theme_use('clam')
        
        lbl_title = ttk.Label(root, text="Logitech G27 Controller Hub", font=("Helvetica", 12, "bold"))
        lbl_title.pack(pady=10)
        
        self.lbl_status = ttk.Label(root, text="Status: Initializing...", font=("Helvetica", 10))
        self.lbl_status.pack(pady=5)
        
        progress_frame = ttk.Frame(root)
        progress_frame.pack(pady=10, fill='x', padx=20)  
        
        self.lbl_travel = ttk.Label(progress_frame, text="Pedal Pressure: 0%")
        self.lbl_travel.pack(anchor='w')
        
        self.progress = ttk.Progressbar(progress_frame, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(pady=5)
        
        self.btn_close = ttk.Button(root, text="STOP & EXIT ENGINE", command=self.close_application)
        self.btn_close.pack(pady=15)
        
        self.root.protocol("WM_DELETE_WINDOW", self.close_application)
        self.update_gui_elements()

    def update_gui_elements(self):
        global ui_status_text, ui_pedal_pct, running
        if running:
            self.lbl_status.config(text=f"Status: {ui_status_text}")
            self.lbl_travel.config(text=f"Pedal Pressure: {ui_pedal_pct}%")
            self.progress['value'] = ui_pedal_pct
            self.root.after(50, self.update_gui_elements) 

    def close_application(self):
        global running
        print("🛑 Closing interface down gracefully...")
        running = False
        EMERGENCY_RELEASE()
        pygame.quit()
        self.root.destroy()

# Start background input capture
input_thread = threading.Thread(target=core_execution_loop, daemon=True)
input_thread.start()

if __name__ == "__main__":
    root = tk.Tk()
    app = SewingApp(root)
    
    hardware_woken_up = False

    def pygame_pump_cycle():
        global current_pct, running, hardware_woken_up
        if running:
            pygame.event.pump()
            if wheel is not None:
                raw_val = wheel.get_axis(AXIS_INDEX)
                
                if raw_val != 0.0:
                    hardware_woken_up = True
                    
                if not hardware_woken_up:
                    current_pct = 0.0
                else:
                    if INVERT_AXIS:
                        current_pct = max(0.0, min(1.0, (1.0 - raw_val) / 2.0))
                    else:
                        current_pct = max(0.0, min(1.0, (raw_val + 1.0) / 2.0))
                        
            root.after(10, pygame_pump_cycle) 

    root.after(10, pygame_pump_cycle)
    root.mainloop()
