FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    freecad \
    xvfb \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libglx0 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create FreeCAD Mod directory and copy addon
RUN mkdir -p $HOME/.local/share/FreeCAD/Mod
COPY --chown=user addon/FreeCADMCP $HOME/.local/share/FreeCAD/Mod/FreeCADMCP

# Add the addon path to PYTHONPATH so FreeCAD can find it
ENV PYTHONPATH=$HOME/.local/share/FreeCAD/Mod/FreeCADMCP:$PYTHONPATH

COPY --chown=user . .

RUN chmod +x entrypoint.sh

EXPOSE 7860

CMD ["./entrypoint.sh"]
