import onnxruntime as ort
print(f"Available Providers: {ort.get_available_providers()}")
try:
    print(f"Device: {ort.get_device()}")
except:
    print("Could not get device")
