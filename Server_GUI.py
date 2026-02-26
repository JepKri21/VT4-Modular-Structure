import subprocess
import signal
import os
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
import json
import requests
import base64
from pathlib import Path


bash_path = r"C:\Program Files\Git\bin\bash.exe"
script_dir = ".\AasxServerBlazor.v0.3.1.343-aasV3-alpha-latest\AasxServerBlazor"
script_name = "00startForDemo.sh"

shell_folder = ".\Telefon-Produktion\JSON_Shells"
submodel_folder = ".\Telefon-Produktion\JSON_Submodels"

PORT = "5001"
SERVER_BASE = f"http://localhost:{PORT}"  # your server base URL
SUBMODEL_ENDPOINT = f"{SERVER_BASE}/submodels"
SHELL_ENDPOINT = f"{SERVER_BASE}/shells"

class ServerGUI:
    def __init__(self, root):
        self.root = root
        self.process = None  # shared subprocess

        #============================Basic Server Buttons==========================

        # Start button
        self.start_btn = tk.Button(root,text="Start Server",width=18,command=self.start_server)
        self.start_btn.place(x=50, y=40, width=120, height=40)

        # Stop button
        self.stop_btn = tk.Button(root,text="Stop Server",width=18,command=self.stop_server)
        self.stop_btn.place(x=50, y=80, width=120, height=40)

        # Reset button
        self.reset_btn = tk.Button(root,text="Reset Server",width=18,command=self.reset_server)
        self.reset_btn.place(x=50, y=120, width=120, height=40)

        #Post Shell Button
        self.post_shell_btn = tk.Button(root, text="Post Shell", width=18, command=self.post_shell)
        self.post_shell_btn.place(x=200, y=40, width=120, height=40)

        #Post Submodel Button
        self.post_submodel_btn = tk.Button(root, text="Post Submodel", width=18, command=self.post_submodel)
        self.post_submodel_btn.place(x=200, y=80, width=120, height=40)

        #Get Shells Button
        self.get_shells_btn = tk.Button(root, text="Get Shells", width=18, command=self.get_shells)
        self.get_shells_btn.place(x=320, y=200, width=120, height=40)

        #Get Submodels Button
        self.get_submodels_btn = tk.Button(root, text="Get Submodels", width=18, command=self.get_submodels)
        self.get_submodels_btn.place(x=440, y=200, width=120, height=40)

        #Get Shell Button
        self.get_shells_btn = tk.Button(root, text="Get Shell", width=18, command=self.get_shell)
        self.get_shells_btn.place(x=200, y=240, width=120, height=40)

        #Get Submodel Button
        self.get_submodels_btn = tk.Button(root, text="Get Submodel", width=18, command=self.get_submodel)
        self.get_submodels_btn.place(x=200, y=280, width=120, height=40)

        # Post ALL Shells Button
        self.post_all_shells_btn = tk.Button(root,text="Post All Shells",width=18,command=self.post_all_shells)
        self.post_all_shells_btn.place(x=200, y=120, width=120, height=40)

        # Post ALL Submodels Button
        self.post_all_submodels_btn = tk.Button(root,text="Post All Submodels",width=18,command=self.post_all_submodels)
        self.post_all_submodels_btn.place(x=320, y=120, width=140, height=40)


        #============================File Dropboxes================================

        # --- Shell files dropdown (post)---
        self.shell_file_var = tk.StringVar(master=root)
        self.shell_files = ["Nothing Selected"] + self.find_json_files(shell_folder)
        self.shell_dropdown = ttk.Combobox(root,textvariable=self.shell_file_var,values=self.shell_files,state="readonly")
        self.shell_dropdown.place(x=320, y=40, width=650, height=40)
        self.shell_dropdown.current(0)

        # --- Submodel files dropdown (post)---
        self.submodel_file_var = tk.StringVar(master=root)
        self.submodel_files = ["Nothing Selected"] + self.find_json_files(submodel_folder)
        self.submodel_dropdown = ttk.Combobox(root,textvariable=self.submodel_file_var,values=self.submodel_files,state="readonly")
        self.submodel_dropdown.place(x=320, y=80, width=650, height=40)
        self.submodel_dropdown.current(0)

        # --- Shell IDs dropdown (FROM SERVER) ---
        self.shell_id_var = tk.StringVar(master=root)
        self.shell_ids = ["Nothing Selected"]
        self.shell_id_dropdown = ttk.Combobox(root,textvariable=self.shell_id_var,values=self.shell_ids,state="readonly")
        self.shell_id_dropdown.place(x=320, y=240, width=300, height=40)
        self.shell_id_dropdown.current(0)


        # --- Submodel IDs dropdown (FROM SERVER) ---
        self.submodel_id_var = tk.StringVar(master=root)
        self.submodel_ids = ["Nothing Selected"]
        self.submodel_id_dropdown = ttk.Combobox(root,textvariable=self.submodel_id_var,values=self.submodel_ids,state="readonly")
        self.submodel_id_dropdown.place(x=320, y=280, width=300, height=40)
        self.submodel_id_dropdown.current(0)

        #============================Misc============================================

        # --- Hook the window close event ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.terminal_output = ScrolledText(root, state='disabled', width=120, height=20)
        self.terminal_output.place(x=50, y=350, width=600, height=200)

    #=======================================GUI Functions================================0

    def find_json_files(self, folder):
        return [str(p) for p in Path(folder).rglob("*.json")]

    def start_server(self):
        if self.process and self.process.poll() is None:
            self.append_terminal("Server already running")
            return
        self.append_terminal("Starting Server...")
        self.process = subprocess.Popen(
            [bash_path, "-lc", f"./{script_name}"],
            cwd=script_dir,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        self.append_terminal("Server Started")

    def stop_server(self):
        if not self.process or self.process.poll() is not None:
            self.append_terminal("Server is not running")
            return

        self.append_terminal("Stopping server...")
        self.process.send_signal(signal.CTRL_C_EVENT)

        try:
            self.process.wait(timeout=1)
            self.append_terminal("Server stopped cleanly")
        except subprocess.TimeoutExpired:
            self.append_terminal("Graceful stop failed — forcing shutdown")
            self.process.kill()
            self.process.wait()
            self.append_terminal("Server force stopped")

        self.process = None

    def reset_server(self):
        self.append_terminal("Resetting server...")
        self.stop_server()
        self.start_server()
        self.append_terminal("Server Reset")

    def on_close(self):
        if self.process and self.process.poll() is None:
            self.append_terminal("Closing GUI, stopping server first...")
            self.stop_server()
        self.root.destroy()
    
    def post_shell(self):
        selected_file = self.shell_file_var.get()
        if selected_file == "Nothing Selected":
            self.append_terminal("No shell file selected")
            return
        full_path = selected_file
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        response = requests.post(SHELL_ENDPOINT, json=data, headers={"Content-Type": "application/json"})
        self.append_terminal(f"Shell POST ({selected_file}): {response.status_code}")

    def post_submodel(self):
        selected_file = self.submodel_file_var.get()
        if selected_file == "Nothing Selected":
            self.append_terminal("No submodel file selected")
            return
        full_path = selected_file
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        response = requests.post(SUBMODEL_ENDPOINT, json=data, headers={"Content-Type": "application/json"})
        self.append_terminal(f"Submodel POST ({selected_file}): {response.status_code}")

    def get_shells(self):
        self.append_terminal("Getting Shells")
        response = requests.get(SHELL_ENDPOINT)
        data = response.json()
        shells = data.get("result", [])
        self.shell_ids = ["Nothing Selected"] + [shell["id"] for shell in shells]
        self.shell_id_dropdown["values"] = self.shell_ids
        self.shell_id_dropdown.current(0)

    def get_submodels(self):
        self.append_terminal("Getting Submodels")
        response = requests.get(SUBMODEL_ENDPOINT)
        data = response.json()
        submodels = data.get("result", [])
        self.submodel_ids = ["Nothing Selected"] + [submodel["id"] for submodel in submodels]
        self.submodel_id_dropdown["values"] = self.submodel_ids
        self.submodel_id_dropdown.current(0)

    def get_shell(self):
        self.append_terminal("Getting Single Shell")
        self.encoded_shell_id = self.base64encode(self.shell_id_var.get())
        response = requests.get(f"{SHELL_ENDPOINT}/{self.encoded_shell_id}")
        data = response.json()
        print(data)

    def get_submodel(self):
        self.append_terminal("Getting Single Submodel")
        self.encoded_submodel_id = self.base64encode(self.submodel_id_var.get())
        response = requests.get(f"{SUBMODEL_ENDPOINT}/{self.encoded_submodel_id}")
        data = response.json()
        print(data)

    def append_terminal(self, text):
        self.terminal_output.configure(state='normal')
        self.terminal_output.insert(tk.END, text + "\n")
        self.terminal_output.see(tk.END)  # scroll to the end
        self.terminal_output.configure(state='disabled')

    def base64encode(self, value: str):
        encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
        encoded = encoded.rstrip("=")  # remove padding if server expects that
        print(f"Printing encoded string: {encoded}")
        return encoded

    def post_all_shells(self):
        self.append_terminal("Posting ALL shell JSON files...")
        files = list(Path(shell_folder).rglob("*.json"))

        if not files:
            self.append_terminal("No shell JSON files found")
            return
        
        for file_path in files:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            response = requests.post(SHELL_ENDPOINT,json=data,headers={"Content-Type": "application/json"})
            if response.ok:
                self.append_terminal(f"OK  → {file_path.name}")
            else:
                self.append_terminal(f"FAIL ({response.status_code}) → {file_path.name}")

    def post_all_submodels(self):
        self.append_terminal("Posting ALL submodel JSON files...")
        files = list(Path(submodel_folder).rglob("*.json"))

        if not files:
            self.append_terminal("No submodel JSON files found")
            return

        for file_path in files:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            response = requests.post(SUBMODEL_ENDPOINT,json=data,headers={"Content-Type": "application/json"})
            if response.ok:
                self.append_terminal(f"OK  → {file_path.name}")
            else:
                self.append_terminal(f"FAIL ({response.status_code}) → {file_path.name}")



root = tk.Tk()
root.title("AAS Server Controller")
root.geometry("760x780")        # width x height
root.resizable(True, True)
app = ServerGUI(root)
root.mainloop()
