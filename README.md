# racing controller setup guide  

use your android (or any other device) as a wireless racing controller for pc games that require a steering wheel input — no installation needed on the phone.  

---

## how it works  
- you run a lightweight python server (`racing_server.py`) on your pc  
- your phone (or any device) connects via browser and acts as the controller  
- both devices must be on the same network  

---

## prerequisites  
- **python installed** on your pc  
- `racing_server.py` file downloaded and placed in a dedicated folder  

---

## installation steps  

open terminal in the same folder as `racing_server.py`, then run:  

```bash
pip install vgamepad websockets
pip install websockets pyautogui
pip install pyvjoy websockets
```

---

## running the server

`python racing_server.py`

- the terminal will display a link
- open that link in your phone’s browser
- ensure both pc and phone are connected to the same network
