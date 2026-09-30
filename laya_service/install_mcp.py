"""Backward compatibility shim for laya_service.install_mcp -> systemone.install_mcp."""
from systemone.install_mcp import *

if __name__ == "__main__":
    main()