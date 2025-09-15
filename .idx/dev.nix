{ pkgs, ... }: {
  channel = "stable-24.05";
  packages = [
    pkgs.python3
    pkgs.tesseract5
    # pkgs.tessdata_best  # Comentado temporalmente para arreglar la compilación
    pkgs.pkg-config
    pkgs.gcc
    pkgs.stdenv.cc.cc.lib
    pkgs.libGL
    pkgs.zlib
    pkgs.gcc-unwrapped.lib
  ];
  env = {
    LD_LIBRARY_PATH = pkgs.lib.mkForce "${pkgs.stdenv.cc.cc.lib}/lib";
  };
  idx = {
    extensions = [ "ms-python.python" ];
    workspace = {
      onStart = {
        install-deps = ''
          if [ ! -d ".venv" ]; then
            echo "Creating virtual environment in ./.venv..."
            python -m venv .venv
          fi
          echo "Installing dependencies from requirements.txt..."
          source .venv/bin/activate
          pip install --no-cache-dir --force-reinstall -r requirements.txt
        '';
        open-readme = {
          openFiles = [ "README.md" "main.py" ];
        };
      };
    };
    previews = {
      enable = true;
      previews = {
        web = {
          command = ["./devserver.sh"];
          manager = "web";
        };
      };
    };
  };
}
