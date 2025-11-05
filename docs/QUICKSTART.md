# Quick Start Guide

Get started with FreeCAD MCP in 5 minutes!

## Prerequisites

- ✅ Python 3.10 or higher
- ✅ FreeCAD 0.21 or higher installed
- ✅ Claude Desktop installed

## Step 1: Install FreeCAD Addon (2 minutes)

### Locate Your FreeCAD Addon Directory

**Windows:**
```
%APPDATA%\FreeCAD\Mod\
```
Usually: `C:\Users\YourName\AppData\Roaming\FreeCAD\Mod\`

**Mac:**
```
~/Library/Application Support/FreeCAD/Mod/
```

**Linux:**
- Ubuntu: `~/.FreeCAD/Mod/`
- Ubuntu (snap): `~/snap/freecad/common/Mod/`
- Debian: `~/.local/share/FreeCAD/Mod`

### Install the Addon

```bash
# Clone the repository
git clone https://github.com/neka-nat/freecad-mcp.git
cd freecad-mcp

# Copy addon (adjust path for your OS)
# Windows
xcopy /E /I addon\FreeCADMCP "%APPDATA%\FreeCAD\Mod\FreeCADMCP"

# Mac/Linux
cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/
```

## Step 2: Start FreeCAD Server (30 seconds)

1. **Launch FreeCAD**
   
2. **Select MCP Addon Workbench**
   - Find "MCP Addon" in the workbench dropdown
   
3. **Start RPC Server**
   - Click "Start RPC Server" button in toolbar
   - Server starts on port 9875
   - You should see confirmation message

![Start Server](../assets/start_rpc_server.png)

## Step 3: Configure Claude Desktop (1 minute)

### Find Config File

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Mac:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

### Add Configuration

Open the file and add:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": ["freecad-mcp"]
    }
  }
}
```

**Optional: Text-only mode** (saves tokens, no screenshots):
```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": ["freecad-mcp", "--only-text-feedback"]
    }
  }
}
```

### Restart Claude Desktop

Close and reopen Claude Desktop for changes to take effect.

## Step 4: Test It! (1 minute)

Open Claude Desktop and try these commands:

### Test 1: Simple Box
```
Create a box 100mm x 50mm x 30mm
```

**Expected:** Box created in FreeCAD with screenshot

### Test 2: Advanced Shape
```
Create a cylinder with radius 20mm and height 50mm, 
then add a fillet of 5mm to the top edge
```

**Expected:** Cylinder with rounded top edge

### Test 3: Symmetric Part
```
Create a cube 50mm on each side, then mirror it across the YZ plane
```

**Expected:** Two cubes side by side

## 🎉 Success!

You're now ready to use FreeCAD with Claude!

## Next Steps

### Learn More

- **[User Guide](USER_GUIDE.md)** - Complete feature documentation
- **[Corsair Workflow](CORSAIR_MODELING_WORKFLOW.md)** - Advanced aircraft modeling
- **[API Reference](API_REFERENCE.md)** - All available tools

### Try These Examples

#### Example 1: Design a Flange
```
Create a flange for a pipe:
1. Create a cylinder 100mm diameter, 20mm thick
2. Add 6 bolt holes in a circular pattern at 80mm diameter
3. Each hole is 10mm diameter
```

#### Example 2: Aircraft Wing Profile
```
Create an aircraft wing:
1. Import NACA 2412 airfoil profile with 2000mm chord length
2. Extrude it 6000mm to create a wing
3. Mirror it to create both wings
```

#### Example 3: Radial Engine
```
Create a radial engine cylinder arrangement:
1. Create one cylinder 50mm diameter, 100mm long
2. Use circular pattern to create 18 cylinders around an axis
```

## Troubleshooting

### Problem: Claude doesn't see FreeCAD tools

**Solution:**
1. Check FreeCAD RPC server is running (green indicator)
2. Restart Claude Desktop
3. Verify config file syntax is correct

### Problem: "Connection refused"

**Solution:**
1. Make sure FreeCAD is running
2. Click "Start RPC Server" in FreeCAD
3. Check firewall allows localhost:9875

### Problem: No screenshot in responses

**Solution:**
1. Switch to 3D view in FreeCAD (not TechDraw/Spreadsheet)
2. Or use `--only-text-feedback` flag if screenshots not needed

### Problem: Tools not executing

**Solution:**
1. Check FreeCAD console for error messages
2. Try executing code manually in FreeCAD Python console
3. Verify FreeCAD version is 0.21 or higher

## Getting Help

- **GitHub Issues**: [Report bugs or request features](https://github.com/neka-nat/freecad-mcp/issues)
- **Documentation**: Check [User Guide](USER_GUIDE.md)
- **FreeCAD Forum**: [Ask FreeCAD questions](https://forum.freecad.org/)

## Tips & Tricks

### 💡 Be Specific
Instead of: "Make a part"
Try: "Create a rectangular part 100mm x 50mm x 20mm"

### 💡 Use Step-by-Step
For complex parts, describe operations one by one:
```
1. Create a cylinder 50mm diameter, 100mm height
2. Add a 10mm fillet to the top edge
3. Mirror it across the XZ plane
4. Move the copy 100mm in the Y direction
```

### 💡 Reference Existing Objects
```
"Add a hole to the top face of Box001"
"Mirror Cylinder001 across the YZ plane"
```

### 💡 Save Your Work
FreeCAD doesn't auto-save. In FreeCAD:
```
File > Save As > choose location
```

### 💡 Visualize Results
Ask for specific views:
```
"Show me the top view"
"Show me an isometric view"
```

## What's Next?

Now that you have FreeCAD MCP working, explore:

1. **[Complete User Guide](USER_GUIDE.md)** - All 52 tools explained
2. **[Corsair Workflow](CORSAIR_MODELING_WORKFLOW.md)** - Real-world aircraft project
3. **[Contributing](../CONTRIBUTING.md)** - Help improve FreeCAD MCP

---

**Ready to design? Start creating with Claude and FreeCAD!** 🚀

