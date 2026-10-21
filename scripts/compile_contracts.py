"""
Compile test-only contracts (TestToken, TestAMM, TestSagaVault) to produce ABI and Bytecode artifacts.
"""

import json
from pathlib import Path
import solcx

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = REPO_ROOT / "contracts"
ARTIFACTS_DIR = REPO_ROOT / "assets" / "contracts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

solcx.set_solc_version("0.8.24")

files = [
    str(CONTRACTS_DIR / "TestToken.sol"),
    str(CONTRACTS_DIR / "TestAMM.sol"),
    str(CONTRACTS_DIR / "TestSagaVault.sol"),
]

print("Compiling contracts with solc 0.8.24...")
compiled = solcx.compile_files(
    files,
    output_values=["abi", "bin", "bin-runtime"],
)

result = {}
for key, data in compiled.items():
    name = key.split(":")[-1]
    bin_hex = data.get("bin", "")
    rt_hex = data.get("bin-runtime", "")
    result[name] = {
        "contract_name": name,
        "abi": data.get("abi", []),
        "bytecode": "0x" + bin_hex,
        "runtime_bytecode": "0x" + rt_hex,
    }
    print(f" -> Compiled {name}: bytecode length = {len(bin_hex)} hex characters")

output_path = ARTIFACTS_DIR / "compiled_contracts.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2)

print(f"[SUCCESS] Exported compilation artifacts to: {output_path}")
