import os
import sys
import subprocess
import signal

class ConversionTask:
    """
    Handles the logic for a single file conversion task using FFmpeg.
    """

    def __init__(self, input_path, output_format):
        self.input_path = input_path
        self.output_format = output_format.lower()
        self.output_path = self._generate_output_path()
        self.process = None
        self.is_cancelled = False
        
        # Locate the ffmpeg executable
        self.ffmpeg_exe = self._get_ffmpeg_path()

    def _get_ffmpeg_path(self):
        """
        Locates the ffmpeg binary. 
        Compatible with development environment and PyInstaller one-file mode.
        """
        if getattr(sys, 'frozen', False):
            # If the app is packaged with PyInstaller, use the temp folder
            base_path = sys._MEIPASS
        else:
            # If running from source, use the project root
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        ffmpeg_path = os.path.join(base_path, 'bin', 'ffmpeg.exe')
        
        if not os.path.exists(ffmpeg_path):
            raise FileNotFoundError(f"FFmpeg binary not found at: {ffmpeg_path}")
            
        return ffmpeg_path

    def _generate_output_path(self):
        """
        Generates the output filename by replacing the extension.
        Example: C:/Videos/movie.mkv -> C:/Videos/movie.mp4
        """
        base_name = os.path.splitext(self.input_path)[0]
        return f"{base_name}.{self.output_format}"

    def run(self):
        """
        Executes the conversion synchronously.
        NOTE: This MUST be run in a separate thread to avoid freezing the GUI.
        """
        if not os.path.exists(self.input_path):
            raise FileNotFoundError(f"Input file not found: {self.input_path}")

        # FFmpeg command construction
        # -y: Overwrite output files without asking
        cmd = [
            self.ffmpeg_exe, 
            '-y', 
            '-i', self.input_path, 
            self.output_path
        ]

        # Windows-specific: Hide the console window
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        try:
            # Launch the process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Wait for finish and capture output
            stdout, stderr = self.process.communicate()

            if self.process.returncode != 0:
                # FFmpeg writes errors to stderr
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise RuntimeError(f"FFmpeg Error: {error_msg}")

        except Exception as e:
            if self.is_cancelled:
                return "Cancelled"
            raise e

        return self.output_path

    def stop(self):
        """
        Stops the running process immediately.
        """
        self.is_cancelled = True
        if self.process:
            # Force kill the process
            self.process.kill()