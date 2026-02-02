import os
from core import FileProber

def test_probe():
    print("--- Testing FFprobe Analysis ---")
    
    # Mettez ici le chemin d'un VRAI fichier vidéo ou audio sur votre PC pour tester
    # Exemple : "C:\\Users\\Mathieu\\Downloads\\video.mp4"
    # Si vous n'en avez pas, le script va essayer de créer un faux fichier (qui donnera une erreur d'analyse, c'est normal)
    
    # Changez ce chemin !
    test_file = "C:\\Windows\\Media\\chimes.wav" 
    
    if not os.path.exists(test_file):
        print(f"Test file not found at: {test_file}")
        print("Please edit main.py and set 'test_file' to a real media file.")
        return

    try:
        prober = FileProber()
        print(f"FFprobe found at: {prober.ffprobe_exe}")
        
        print(f"Analyzing: {test_file} ...")
        meta = prober.analyze(test_file)
        
        print("\n--- Results ---")
        print(f"Filename: {meta.filename}")
        print(f"Format:   {meta.format_long}")
        print(f"Duration: {meta.duration_sec:.2f} seconds")
        print(f"Summary:  {meta.get_summary()}")
        
        if meta.has_audio:
            print(f"Audio Details: {meta.audio_codec}, {meta.audio_bitrate}, {meta.audio_channels} channels")
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    test_probe()