import socket
import subprocess
import time
import webbrowser

from modal import Image, Queue, Stub, forward

stub = Stub("example-a1111-webui")
stub.urls = Queue.new()  # TODO: FunctionCall.get() doesn't support generators.
GPU = "a100" # a10g


def wait_for_port(port: int):
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5.0):
                break
        except OSError:
            time.sleep(0.1)

@stub.function(
    image=Image.debian_slim() # python_version="3.10"
    # template code
    .apt_install(
        "wget",
        "git",
        "libgl1",
        "libglib2.0-0",
        "google-perftools",  # For tcmalloc
    )
    .env({"LD_PRELOAD": "/usr/lib/x86_64-linux-gnu/libtcmalloc.so.4"})
    .run_commands(
        # clone the webui, setup the python environment, install requirements
        "git clone --depth 1 --branch v1.6.0 https://github.com/AUTOMATIC1111/stable-diffusion-webui /webui",
        "python -m venv /webui/venv",
        "cd /webui && . venv/bin/activate && "
        + "python -c 'from modules import launch_utils; launch_utils.prepare_environment()' --xformers",
        gpu=GPU,
    )
    .run_commands(
        # get the controlnet models
        "mkdir /webui/models/ControlNet && " 
        + "cd /webui/models/ControlNet && "
        + "curl https://civitai.com/api/download/models/111973?type=Model&format=SafeTensor && "
        + "curl https://civitai.com/api/download/models/111973?type=Config&format=Other"
        ,
        # clone the extension and run the python thing in it
        "cd /webui/extensions && "
        + "git clone https://github.com/KanishkGar/sd-webui-controlnet.git && "
        + "cd /webui && "
        + "python /webui/extensions/sd-webui-controlnet/install.py"
        ,
        # clone the controlnet qr model into the extension subdirectory
        "cd /webui/extensions/sd-webui-controlnet/models && "
        # + "curl https://huggingface.co/Nacholmo/controlnet-qr-pattern-v2/resolve/main/automatic1111/QRPattern_v2_9500.safetensors"
        + "wget https://huggingface.co/Nacholmo/controlnet-qr-pattern-v2/resolve/main/automatic1111/QRPattern_v2_9500.safetensors"
        ,
        # pre-existing code
        "cd /webui && . venv/bin/activate && "
        + "pip install httpcore==0.17.2 && "
        + "python -c 'from modules import shared_init, initialize; shared_init.initialize(); initialize.initialize()'",
    ),
    gpu=GPU,
    cpu=2,
    memory=1024,
    timeout=3600,
)
# template code
def start_web_ui():
    START_COMMAND = r"""
cd /webui && \
. venv/bin/activate && \
accelerate launch \
    --num_processes=1 \
    --num_machines=1 \
    --mixed_precision=fp16 \
    --dynamo_backend=inductor \
    --num_cpu_threads_per_process=6 \
    /webui/launch.py \ # main function to launch the webui
        --skip-prepare-environment \
        --listen \
        --port 8000 \
        --enable-insecure-extension-access
"""
    # template code to run webui on a website
    with forward(8000) as tunnel:
        p = subprocess.Popen(START_COMMAND, shell=True)
        wait_for_port(8000)
        print("[MODAL] ==> Accepting connections at", tunnel.url)
        stub.urls.put(tunnel.url)
        p.wait(3600)

# template code to run webui on a website
@stub.local_entrypoint()
def main(no_browser: bool = False):
    start_web_ui.spawn()
    url = stub.urls.get()
    if not no_browser:
        webbrowser.open(url)
    while True:  # TODO: FunctionCall.get() doesn't support generators.
        time.sleep(1)
