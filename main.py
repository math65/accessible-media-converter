import os
from core import ConversionTask

def test_backend():
    print("--- Starting Backend Test ---")
    
    # 1. Create a fake file just to test paths
    dummy_input = "test_file.txt"
    with open(dummy_input, "w") as f:
        f.write("Dummy content")
    
    try:
        # 2. Initialize the task (this checks if ffmpeg.exe exists)
        task = ConversionTask(dummy_input, "mp3")
        print(f"[OK] FFmpeg found at: {task.ffmpeg_exe}")
        
        # 3. Try running it (it will fail because txt -> mp3 is impossible, but it proves ffmpeg started)
        print("Attempting to run FFmpeg...")
        task.run()
        
    except FileNotFoundError as e:
        print(f"[ERROR] Path issue: {e}")
    except RuntimeError as e:
        # If we get a Runtime Error from FFmpeg, it means FFmpeg STARTED successfully!
        print(f"[SUCCESS] FFmpeg ran and complained (expected): {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected: {e}")
    finally:
        # Cleanup
        if os.path.exists(dummy_input):
            os.remove(dummy_input)

if __name__ == "__main__":
    test_backend()