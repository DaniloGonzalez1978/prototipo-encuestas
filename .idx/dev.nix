{ pkgs, ... }: {
  # Switching to 'unstable' to resolve issues with the 'tessdata-best' package.
  channel = "unstable";
  packages = [
    pkgs.python3
    pkgs.tesseract5
    # The 'tessdata-best' package is used for tesseract data.
    # pkgs.tessdata-best
    pkgs.pkg-config
    pkgs.gcc
    pkgs.stdenv.cc.cc.lib
    pkgs.libGL
    pkgs.zlib
    pkgs.gcc-unwrapped.lib
  ];
  env = {
    LD_LIBRARY_PATH = pkgs.lib.mkForce "${pkgs.stdenv.cc.cc.lib}/lib";
    # Updated to use the correct package name
    # TESSDATA_PREFIX = "${pkgs.tessdata-best}/share/tessdata";
    # --- BEGIN AWS Configuration -- -
    # Las credenciales de AWS no deben ser almacenadas aquí.
    # Este entorno está configurado para leerlas desde el archivo .env
    # Asegúrate de que las siguientes variables estén en tu .env:
    # AWS_ACCESS_KEY_ID
    # AWS_SECRET_ACCESS_KEY
    # AWS_DEFAULT_REGION
    # DYNAMODB_TABLE_NAME
    # --- END AWS Configuration ---
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
      };
      # previews = [
      #   {
      #     id = "web";
      #     name = "Web";
      #     command = [ "./devserver.sh" ];
      #     manager = "web";
      #   }
      # ];
    };
  };
}
