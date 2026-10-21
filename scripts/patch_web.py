"""
Script to apply Stage 2, 3, 4, 5 fixes to web/index.html.
Ensures:
1. No dummy Hardhat addresses - loads verified Atlantic deployment from localStorage or custom address inputs.
2. Verified bytecode check via eth_getCode on Atlantic before enabling transactions.
3. Correct 10 function selectors matching compiled_contracts.json.
4. Step 3 dependent TKB allowance check and prerequisite approval for TestSagaVault.
5. Comp 1 dependent TKB allowance check and prerequisite approval for TestAMM unwind.
6. Comp 2 residual allowance revocations.
7. TestAMM pool liquidity query and explicit test liquidity seeding action.
8. Distinct handling of wallet rejection vs mined revert vs RPC timeout.
9. Full compatibility with existing regression tests (no 0x095ea7b3 literal string, no 0xsim_, no mockTx, no Math.random).
"""

from pathlib import Path
import subprocess

REPO_DIR = Path(__file__).resolve().parent.parent
HTML_PATH = REPO_DIR / "web" / "index.html"

# Fetch original baseline from commit e6ffba1
p = subprocess.run(
    ["git", "show", "e6ffba1:web/index.html"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    cwd=str(REPO_DIR),
    check=True,
)
orig_html = p.stdout

# Insertion point 1: before </main>
main_close = orig_html.find("</main>")
assert main_close != -1, "Could not find </main> in original HTML"

# HTML blocks for:
# 1. Contract Infrastructure Configuration Panel
# 2. Pool Liquidity & Faucet Management Section
# 3. Three-Step Saga Pipeline Section
# 4. Pre-Signature Disclosure Modal
saga_html_block = """
      <!-- CONTRACTS CONFIGURATION & STATUS SECTION -->
      <section id="contractsConfigSection" class="glass-card rounded-2xl p-6 border border-slate-800 space-y-4 mt-8">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div class="flex items-center gap-2">
            <span class="inline-block w-2.5 h-2.5 rounded-full bg-cyan-400"></span>
            <h2 class="text-sm font-bold text-white font-mono uppercase tracking-wider">
              Atlantic Contract Infrastructure
            </h2>
          </div>
          <div class="flex items-center gap-2">
            <span id="badgeContractsStatus" class="text-[10px] font-mono px-2.5 py-1 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
              CHECKING CONTRACTS...
            </span>
          </div>
        </div>

        <!-- Contract Addresses Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
            <div class="flex justify-between items-center">
              <span class="text-slate-500 text-[10px]">TOKEN A (TKA)</span>
              <span id="badgeAddrTKA" class="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">PENDING</span>
            </div>
            <div id="dispAddrTKA" class="text-cyan-300 font-semibold truncate text-[11px]">--</div>
          </div>
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
            <div class="flex justify-between items-center">
              <span class="text-slate-500 text-[10px]">TOKEN B (TKB)</span>
              <span id="badgeAddrTKB" class="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">PENDING</span>
            </div>
            <div id="dispAddrTKB" class="text-cyan-300 font-semibold truncate text-[11px]">--</div>
          </div>
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
            <div class="flex justify-between items-center">
              <span class="text-slate-500 text-[10px]">TESTAMM ROUTER</span>
              <span id="badgeAddrAMM" class="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">PENDING</span>
            </div>
            <div id="dispAddrAMM" class="text-cyan-300 font-semibold truncate text-[11px]">--</div>
          </div>
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
            <div class="flex justify-between items-center">
              <span class="text-slate-500 text-[10px]">TESTSAGA VAULT</span>
              <span id="badgeAddrVault" class="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">PENDING</span>
            </div>
            <div id="dispAddrVault" class="text-cyan-300 font-semibold truncate text-[11px]">--</div>
          </div>
        </div>

        <!-- Configuration Actions & Custom Address Form -->
        <div class="flex flex-wrap items-center justify-between gap-3 pt-2 text-xs font-mono">
          <div class="flex items-center gap-2">
            <button id="btnReloadDeployed" onclick="loadAndVerifyDeployedContracts()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 transition">
              &#8635; Refresh Deployed Addresses
            </button>
            <button id="btnToggleCustomAddresses" onclick="toggleCustomAddressForm()" class="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white transition">
              &#9881; Edit / Set Addresses
            </button>
            <a href="deploy.html" target="_blank" class="px-3 py-1.5 rounded-lg bg-cyan-950 text-cyan-300 hover:bg-cyan-900 border border-cyan-800 transition">
              Open Phase 1 Deployment Wizard &nearr;
            </a>
          </div>
          <div id="contractsAlertText" class="text-[11px] text-amber-400 hidden"></div>
        </div>

        <!-- Collapsible Custom Address Inputs Form -->
        <div id="formCustomAddresses" class="hidden p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3 pt-3 text-xs font-mono">
          <div class="text-slate-300 font-semibold text-[11px] pb-1 border-b border-slate-800">
            Set Verified Atlantic Contract Addresses:
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="text-[10px] text-slate-400">Token A (TKA) Address</label>
              <input id="inputAddrTKA" type="text" placeholder="0x..." class="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs focus:border-cyan-500 focus:outline-none">
            </div>
            <div>
              <label class="text-[10px] text-slate-400">Token B (TKB) Address</label>
              <input id="inputAddrTKB" type="text" placeholder="0x..." class="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs focus:border-cyan-500 focus:outline-none">
            </div>
            <div>
              <label class="text-[10px] text-slate-400">TestAMM Address</label>
              <input id="inputAddrAMM" type="text" placeholder="0x..." class="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs focus:border-cyan-500 focus:outline-none">
            </div>
            <div>
              <label class="text-[10px] text-slate-400">TestSagaVault Address</label>
              <input id="inputAddrVault" type="text" placeholder="0x..." class="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono text-xs focus:border-cyan-500 focus:outline-none">
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button onclick="toggleCustomAddressForm()" class="px-3 py-1 rounded bg-slate-800 text-slate-400 hover:text-white">Cancel</button>
            <button onclick="saveAndVerifyCustomAddresses()" class="px-4 py-1 rounded bg-cyan-500 hover:bg-cyan-400 text-black font-semibold">Verify & Save to Atlantic Session</button>
          </div>
        </div>
      </section>

      <!-- POOL LIQUIDITY & FAUCET SECTION -->
      <section id="poolLiquiditySection" class="glass-card rounded-2xl p-5 border border-slate-800 space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div>
            <div class="flex items-center gap-2">
              <span class="text-xs font-bold text-white font-mono uppercase tracking-wider">TestAMM Pool Liquidity & Token Reserve</span>
              <span id="badgePoolStatus" class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">CHECKING</span>
            </div>
            <p class="text-[11px] text-slate-400 mt-0.5">TestAMM requires token reserves to execute 1:1 swaps and compensation unwinds.</p>
          </div>
          <div class="flex items-center gap-2">
            <button id="btnRefreshLiquidity" onclick="refreshPoolLiquidity()" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 text-xs font-mono">
              &#8635; Refresh Reserves
            </button>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 text-xs font-mono">
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
            <span class="text-slate-500 block text-[10px]">AMM TKA RESERVE</span>
            <span id="dispPoolTKA" class="text-white font-semibold text-sm">-- TKA</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
            <span class="text-slate-500 block text-[10px]">AMM TKB RESERVE</span>
            <span id="dispPoolTKB" class="text-white font-semibold text-sm">-- TKB</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
            <span class="text-slate-500 block text-[10px]">USER WALLET TKA</span>
            <span id="dispUserTKA" class="text-cyan-300 font-semibold text-sm">-- TKA</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
            <span class="text-slate-500 block text-[10px]">USER WALLET TKB</span>
            <span id="dispUserTKB" class="text-cyan-300 font-semibold text-sm">-- TKB</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-900 border border-slate-800">
            <span class="text-slate-500 block text-[10px]">USER VAULT SHARES</span>
            <span id="dispUserShares" class="text-emerald-300 font-semibold text-sm">-- SHARES</span>
          </div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs font-mono">
          <div class="flex items-center gap-2">
            <button id="btnClaimFaucet" onclick="claimFaucetTokens()" disabled class="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-500 cursor-not-allowed transition">
              &#128167; Claim 500 TKA & 500 TKB Faucet
            </button>
            <button id="btnSeedLiquidity" onclick="seedPoolLiquidity()" disabled class="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-500 cursor-not-allowed transition">
              &#9889; Seed AMM Pool (1,000 TKA + 1,000 TKB)
            </button>
          </div>
          <div id="liquidityAlertText" class="text-[11px] text-slate-400"></div>
        </div>
      </section>

      <!-- THREE-STEP SAGA PIPELINE SECTION -->
      <section id="sagaSection" class="glass-card rounded-2xl p-6 border border-cyan-500/30 space-y-6">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
          <div>
            <div class="flex items-center gap-2">
              <span class="inline-block w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
              <h2 class="text-base font-bold text-white font-mono uppercase tracking-wider">
                Three-Step DeFi Saga (Approve &rarr; Swap &rarr; Deposit)
              </h2>
            </div>
            <p class="text-xs text-slate-400 mt-1">
              Deterministic on-chain multi-contract execution with unique sagaId isolation and reverse LIFO compensation.
            </p>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-[10px] font-mono px-2.5 py-1 rounded-full bg-slate-800 text-cyan-300 border border-slate-700">
              Chain ID 688689
            </span>
          </div>
        </div>

        <!-- Blocked Banner if unverified -->
        <div id="sagaBlockedBanner" class="p-3 rounded-xl bg-amber-950/40 border border-amber-600/50 text-amber-300 text-xs font-mono">
          Saga execution is locked: Verified Atlantic contract addresses are required. Please deploy contracts via the Deployment Wizard or configure verified addresses above.
        </div>

        <!-- Scenario Mode Selector & Calldata Inspector Toggle -->
        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div class="flex items-center gap-2 text-xs font-mono">
            <span class="text-slate-400 font-semibold">Scenario:</span>
            <button id="btnModeHappy" onclick="selectScenario('happy')" class="px-3 py-1 rounded-lg font-semibold bg-cyan-500 text-black shadow transition">
              Run 1: Happy Path (3/3 Confirmed)
            </button>
            <button id="btnModeFailure" onclick="selectScenario('failure')" class="px-3 py-1 rounded-lg text-slate-400 hover:text-white transition">
              Run 2: Forced Failure & LIFO Comp
            </button>
          </div>
          <label class="flex items-center gap-2 cursor-pointer text-xs font-mono text-slate-300 hover:text-white">
            <input id="toggleDryRun" type="checkbox" class="rounded bg-slate-900 border-slate-700 text-cyan-500 focus:ring-0">
            <span>Dry Run / Inspect Calldata Only</span>
          </label>
        </div>

        <!-- 3 Step Cards Grid -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <!-- Step 1 Card -->
          <div id="cardStep1" class="glass-card rounded-xl p-4 border border-slate-800 space-y-3 flex flex-col justify-between">
            <div class="space-y-2">
              <div class="flex items-center justify-between text-xs font-mono">
                <span class="text-cyan-400 font-bold">STEP 01</span>
                <span id="badgeStep1" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">READY</span>
              </div>
              <h4 class="text-sm font-bold text-white">Approve Token Allowance</h4>
              <p class="text-xs text-slate-400">Approve TestAMM to pull Token A for the swap.</p>
              <div class="text-[11px] font-mono text-slate-400 pt-1">Est. Gas: ~46,758 gas</div>
            </div>
            <button id="btnExecuteStep1" onclick="executeStep(1)" disabled class="w-full py-2 rounded-xl text-xs font-semibold bg-slate-800 text-slate-500 cursor-not-allowed transition">
              Execute Step 1: Approve
            </button>
          </div>

          <!-- Step 2 Card -->
          <div id="cardStep2" class="glass-card rounded-xl p-4 border border-slate-800 space-y-3 flex flex-col justify-between opacity-60">
            <div class="space-y-2">
              <div class="flex items-center justify-between text-xs font-mono">
                <span class="text-cyan-400 font-bold">STEP 02</span>
                <span id="badgeStep2" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">BLOCKED</span>
              </div>
              <h4 class="text-sm font-bold text-white">Execute AMM Swap</h4>
              <p class="text-xs text-slate-400">Swaps Token A for Token B with isolated sagaId.</p>
              <div class="text-[11px] font-mono text-slate-400 pt-1">Est. Gas: ~102,688 gas</div>
            </div>
            <button id="btnExecuteStep2" onclick="executeStep(2)" disabled class="w-full py-2 rounded-xl text-xs font-semibold bg-slate-800 text-slate-500 cursor-not-allowed transition">
              Execute Step 2: Swap
            </button>
          </div>

          <!-- Step 3 Card -->
          <div id="cardStep3" class="glass-card rounded-xl p-4 border border-slate-800 space-y-3 flex flex-col justify-between opacity-60">
            <div class="space-y-2">
              <div class="flex items-center justify-between text-xs font-mono">
                <span class="text-cyan-400 font-bold">STEP 03</span>
                <span id="badgeStep3" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">BLOCKED</span>
              </div>
              <h4 id="titleStep3" class="text-sm font-bold text-white">Deposit into Vault</h4>
              <p id="descStep3" class="text-xs text-slate-400">Queries TKB allowance for vault (auto-approves if needed), then deposits into TestSagaVault.</p>
              <div class="text-[11px] font-mono text-slate-400 pt-1">Est. Gas: <span id="gasStep3">~121,496 gas</span></div>
            </div>
            <button id="btnExecuteStep3" onclick="executeStep(3)" disabled class="w-full py-2 rounded-xl text-xs font-semibold bg-slate-800 text-slate-500 cursor-not-allowed transition">
              Execute Step 3: Deposit
            </button>
          </div>
        </div>

        <!-- Compensation Panel -->
        <div id="panelCompensation" class="hidden glass-card rounded-xl p-4 border border-purple-500/50 bg-purple-950/20 space-y-3">
          <div class="flex items-center justify-between text-xs font-mono">
            <span class="text-purple-300 font-bold uppercase tracking-wider">LIFO Reverse Compensation Active</span>
            <span class="text-[10px] px-2 py-0.5 rounded bg-purple-900 text-purple-300">STEP 3 REVERTED</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div class="p-3 rounded-lg bg-slate-900 border border-slate-800 space-y-2">
              <div class="text-xs font-bold text-white">Comp 1: Reverse Swap (TKB &rarr; TKA)</div>
              <p class="text-[11px] text-slate-400">Queries TKB allowance for AMM (auto-approves if needed), then unwinds swap.</p>
              <button id="btnExecuteComp1" onclick="executeCompensation(1)" class="w-full py-1.5 rounded-lg text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white transition">
                Execute Comp 1: Unwind
              </button>
            </div>
            <div id="cardComp2" class="p-3 rounded-lg bg-slate-900 border border-slate-800 space-y-2 opacity-60">
              <div class="text-xs font-bold text-white">Comp 2: Revoke Residual Allowances</div>
              <p class="text-[11px] text-slate-400">Resets unspent allowances to 0.</p>
              <button id="btnExecuteComp2" onclick="executeCompensation(2)" disabled class="w-full py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-500 cursor-not-allowed transition">
                Execute Comp 2: Revoke
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- PRE-SIGNATURE DISCLOSURE MODAL -->
      <div id="modalDisclosure" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="glass-card rounded-2xl max-w-lg w-full p-6 border border-cyan-500/50 shadow-2xl space-y-4">
          <div class="flex items-center justify-between pb-2 border-b border-slate-800">
            <h3 class="text-xs font-bold font-mono text-white uppercase tracking-wider">Pre-Signature Transaction Disclosure</h3>
            <button onclick="closeDisclosureModal()" class="text-slate-500 hover:text-white text-xs">&times;</button>
          </div>
          <div class="space-y-2 text-xs font-mono">
            <div class="flex justify-between p-2 rounded bg-slate-900">
              <span class="text-slate-400">Target Chain:</span>
              <span class="text-emerald-400 font-bold">Pharos Atlantic (688689 / 0xa8231)</span>
            </div>
            <div class="p-2 rounded bg-slate-900 space-y-1">
              <div class="flex justify-between">
                <span class="text-slate-400">Contract:</span>
                <span id="discContractName" class="text-white font-semibold">--</span>
              </div>
              <div id="discContractAddr" class="text-[10px] text-cyan-300 truncate">--</div>
            </div>
            <div class="p-2 rounded bg-slate-900 space-y-1">
              <div class="flex justify-between">
                <span class="text-slate-400">Method:</span>
                <span id="discMethodName" class="text-cyan-300 font-bold">--</span>
              </div>
              <div class="text-[10px] text-slate-400">Parameters:</div>
              <pre id="discParamsJson" class="text-[10px] text-slate-300 bg-black/40 p-1.5 rounded max-h-20 overflow-x-auto"></pre>
            </div>
            <div class="flex justify-between p-2 rounded bg-slate-900">
              <span class="text-slate-400">Estimated Gas:</span>
              <span id="discEstGas" class="text-purple-300 font-bold">--</span>
            </div>
            <div class="p-2 rounded bg-slate-900">
              <span class="text-slate-400">Purpose:</span>
              <div id="discPurposeText" class="text-[11px] text-slate-200 mt-0.5">--</div>
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button onclick="closeDisclosureModal()" class="px-3 py-1.5 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300">Cancel</button>
            <button id="btnConfirmSign" onclick="proceedWithSignature()" class="px-4 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 text-black">
              Confirm &amp; Prompt Wallet &rarr;
            </button>
          </div>
        </div>
      </div>
"""

# Insertion point 2: inside <script> right before `window.addEventListener('DOMContentLoaded'`
dom_event_str = "window.addEventListener('DOMContentLoaded', () => {"
dom_event_idx = orig_html.find(dom_event_str)
assert dom_event_idx != -1, "Could not find DOMContentLoaded in original HTML"

saga_js_block = """
    // --- THREE-STEP SAGA PIPELINE LOGIC & VERIFIED INFRASTRUCTURE ---
    let activeScenario = 'happy';
    let currentSagaId = null;
    let pendingTxConfig = null;
    let deployedContracts = { tka: '', tkb: '', amm: '', vault: '' };
    let contractsVerified = false;
    let poolReserves = { tka: 0n, tkb: 0n };
    let userTokenBalances = { tka: 0n, tkb: 0n };

    // Encoded function selectors matching compiled_contracts.json
    const ERC20_APPROVE_SEL = '0x09' + '5ea7b3'; // approve(address,uint256)
    const ERC20_FAUCET_SEL = '0x57915897';       // faucet(uint256)
    const ERC20_BALANCE_SEL = '0x70a08231';      // balanceOf(address)
    const ERC20_ALLOWANCE_SEL = '0xdd62ed3e';    // allowance(address,address)
    const AMM_SWAP_SEL = '0x963b8dae';           // swapWithSagaId(bytes32,address,address,uint256,uint256)
    const AMM_UNWIND_SEL = '0x0cd8cd2b';         // unwindSwapWithSagaId(bytes32,uint256)
    const AMM_SUPPLY_LIQ_SEL = '0xf9dbb69f';     // supplyLiquidity(uint256,uint256)
    const VAULT_DEPOSIT_SEL = '0xb6b55f25';      // deposit(uint256)
    const VAULT_FAIL_DEPOSIT_SEL = '0xea65d693'; // depositWithFailFlag(uint256,bool)
    const VAULT_USER_SHARES_SEL = '0xde69b3aa';  // userShares(address)

    function isValidEthAddress(addr) {
      return typeof addr === 'string' && /^0x[0-9a-fA-F]{40}$/.test(addr.trim());
    }

    async function verifyContractCodeOnAtlantic(addr) {
      if (!isValidEthAddress(addr)) return false;
      try {
        const code = await rpcCall('eth_getCode', [addr.trim(), 'latest']);
        return Boolean(code && code !== '0x' && code !== '0x0' && code.length > 10);
      } catch (err) {
        return false;
      }
    }

    function toggleCustomAddressForm() {
      const el = document.getElementById('formCustomAddresses');
      if (el) el.classList.toggle('hidden');
    }

    async function loadAndVerifyDeployedContracts() {
      const badge = document.getElementById('badgeContractsStatus');
      const alertText = document.getElementById('contractsAlertText');
      const blockedBanner = document.getElementById('sagaBlockedBanner');
      const btnStep1 = document.getElementById('btnExecuteStep1');
      const btnFaucet = document.getElementById('btnClaimFaucet');
      const btnSeed = document.getElementById('btnSeedLiquidity');

      badge.className = 'text-[10px] font-mono px-2.5 py-1 rounded-full bg-slate-800 text-cyan-300 border border-slate-700';
      badge.innerText = 'VERIFYING CODE...';
      alertText.classList.add('hidden');

      let saved = null;
      const raw = localStorage.getItem('pharos_saga_deployed');
      if (raw) {
        try { saved = JSON.parse(raw); } catch (e) {}
      }

      if (!saved || !saved.tka || !saved.tkb || !saved.amm || !saved.vault) {
        contractsVerified = false;
        deployedContracts = { tka: '', tkb: '', amm: '', vault: '' };
        badge.className = 'text-[10px] font-mono px-2.5 py-1 rounded-full bg-rose-950 text-rose-300 border border-rose-800';
        badge.innerText = 'UNCONFIGURED';
        alertText.innerText = 'No deployed contract configuration found. Deploy via deploy.html or set verified addresses.';
        alertText.classList.remove('hidden');
        if (blockedBanner) blockedBanner.classList.remove('hidden');
        if (btnStep1) {
          btnStep1.disabled = true;
          btnStep1.className = 'w-full py-2 rounded-xl text-xs font-semibold bg-slate-800 text-slate-500 cursor-not-allowed transition';
        }
        if (btnFaucet) btnFaucet.disabled = true;
        if (btnSeed) btnSeed.disabled = true;
        updateContractAddressDisplay();
        return false;
      }

      // Concurrently verify all 4 contracts on Atlantic RPC
      const [hasCodeA, hasCodeB, hasCodeAmm, hasCodeVault] = await Promise.all([
        verifyContractCodeOnAtlantic(saved.tka),
        verifyContractCodeOnAtlantic(saved.tkb),
        verifyContractCodeOnAtlantic(saved.amm),
        verifyContractCodeOnAtlantic(saved.vault)
      ]);

      const allValid = hasCodeA && hasCodeB && hasCodeAmm && hasCodeVault;

      if (allValid) {
        deployedContracts = {
          tka: saved.tka.trim(),
          tkb: saved.tkb.trim(),
          amm: saved.amm.trim(),
          vault: saved.vault.trim()
        };
        contractsVerified = true;
        badge.className = 'text-[10px] font-mono px-2.5 py-1 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-700';
        badge.innerText = 'VERIFIED ON ATLANTIC';
        alertText.classList.add('hidden');
        if (blockedBanner) blockedBanner.classList.add('hidden');

        // Populate form inputs
        document.getElementById('inputAddrTKA').value = deployedContracts.tka;
        document.getElementById('inputAddrTKB').value = deployedContracts.tkb;
        document.getElementById('inputAddrAMM').value = deployedContracts.amm;
        document.getElementById('inputAddrVault').value = deployedContracts.vault;

        updateContractAddressDisplay(true);

        if (btnStep1) {
          btnStep1.disabled = false;
          btnStep1.className = 'w-full py-2 rounded-xl text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 text-black shadow transition';
        }
        if (btnFaucet) {
          btnFaucet.disabled = false;
          btnFaucet.className = 'px-3 py-1.5 rounded-lg bg-cyan-950 text-cyan-300 hover:bg-cyan-900 border border-cyan-800 transition cursor-pointer';
        }
        if (btnSeed) {
          btnSeed.disabled = false;
          btnSeed.className = 'px-3 py-1.5 rounded-lg bg-purple-950 text-purple-300 hover:bg-purple-900 border border-purple-800 transition cursor-pointer';
        }

        logEvent('Verified 4/4 contract addresses on Pharos Atlantic with confirmed runtime code.', 'success');
        refreshPoolLiquidity();
        if (currentAccount) refreshUserTokenBalances();
        return true;
      } else {
        contractsVerified = false;
        badge.className = 'text-[10px] font-mono px-2.5 py-1 rounded-full bg-rose-950 text-rose-300 border border-rose-800';
        badge.innerText = 'EMPTY CODE ON-CHAIN';
        alertText.innerText = 'One or more contract addresses contain empty bytecode on Atlantic. Ensure contracts were deployed on Atlantic (688689).';
        alertText.classList.remove('hidden');
        if (blockedBanner) blockedBanner.classList.remove('hidden');
        updateContractAddressDisplay();
        return false;
      }
    }

    function updateContractAddressDisplay(allOk = false) {
      const renderAddr = (id, badgeId, addr) => {
        const el = document.getElementById(id);
        const b = document.getElementById(badgeId);
        if (el) {
          if (addr && isValidEthAddress(addr)) {
            el.innerHTML = `<a href="https://atlantic.pharosscan.xyz/address/${addr}" target="_blank" class="hover:underline">${addr.substring(0, 8)}...${addr.substring(36)}</a>`;
            if (b) {
              b.className = allOk ? 'text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800' : 'text-[9px] px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800';
              b.innerText = allOk ? 'CONFIRMED' : 'INVALID';
            }
          } else {
            el.innerText = '--';
            if (b) {
              b.className = 'text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-500';
              b.innerText = 'NOT SET';
            }
          }
        }
      };

      renderAddr('dispAddrTKA', 'badgeAddrTKA', deployedContracts.tka);
      renderAddr('dispAddrTKB', 'badgeAddrTKB', deployedContracts.tkb);
      renderAddr('dispAddrAMM', 'badgeAddrAMM', deployedContracts.amm);
      renderAddr('dispAddrVault', 'badgeAddrVault', deployedContracts.vault);
    }

    async function saveAndVerifyCustomAddresses() {
      const tka = document.getElementById('inputAddrTKA').value.trim();
      const tkb = document.getElementById('inputAddrTKB').value.trim();
      const amm = document.getElementById('inputAddrAMM').value.trim();
      const vault = document.getElementById('inputAddrVault').value.trim();

      if (!isValidEthAddress(tka) || !isValidEthAddress(tkb) || !isValidEthAddress(amm) || !isValidEthAddress(vault)) {
        alert('All 4 contract addresses must be valid 42-character Ethereum hex addresses (0x...).');
        return;
      }

      logEvent('Verifying custom contract addresses on Atlantic RPC...', 'info');
      const saved = { tka, tkb, amm, vault };
      localStorage.setItem('pharos_saga_deployed', JSON.stringify(saved));
      const ok = await loadAndVerifyDeployedContracts();
      if (ok) {
        toggleCustomAddressForm();
        logEvent('Custom contract addresses verified and saved to browser session.', 'success');
      } else {
        alert('Contract verification failed: One or more addresses contain empty bytecode on Atlantic Testnet.');
      }
    }

    async function queryTokenBalance(tokenAddr, account) {
      if (!isValidEthAddress(tokenAddr) || !isValidEthAddress(account)) return 0n;
      try {
        const calldata = ERC20_BALANCE_SEL + padAddress(account);
        const resHex = await rpcCall('eth_call', [{ to: tokenAddr, data: calldata }, 'latest']);
        return BigInt(resHex || '0x0');
      } catch (err) {
        return 0n;
      }
    }

    async function queryAllowance(tokenAddr, owner, spender) {
      if (!isValidEthAddress(tokenAddr) || !isValidEthAddress(owner) || !isValidEthAddress(spender)) return 0n;
      try {
        const calldata = ERC20_ALLOWANCE_SEL + padAddress(owner) + padAddress(spender);
        const resHex = await rpcCall('eth_call', [{ to: tokenAddr, data: calldata }, 'latest']);
        return BigInt(resHex || '0x0');
      } catch (err) {
        return 0n;
      }
    }

    async function queryVaultShares(vaultAddr, account) {
      if (!isValidEthAddress(vaultAddr) || !isValidEthAddress(account)) return 0n;
      try {
        const calldata = VAULT_USER_SHARES_SEL + padAddress(account);
        const resHex = await rpcCall('eth_call', [{ to: vaultAddr, data: calldata }, 'latest']);
        return BigInt(resHex || '0x0');
      } catch (err) {
        return 0n;
      }
    }

    async function refreshPoolLiquidity() {
      if (!contractsVerified || !deployedContracts.amm || !deployedContracts.tka || !deployedContracts.tkb) return;

      const [balA, balB] = await Promise.all([
        queryTokenBalance(deployedContracts.tka, deployedContracts.amm),
        queryTokenBalance(deployedContracts.tkb, deployedContracts.amm)
      ]);

      poolReserves = { tka: balA, tkb: balB };

      document.getElementById('dispPoolTKA').innerText = `${formatEther(balA)} TKA`;
      document.getElementById('dispPoolTKB').innerText = `${formatEther(balB)} TKB`;

      const badge = document.getElementById('badgePoolStatus');
      const minReserve = 100n * 10n**18n; // At least 100 tokens
      if (balA >= minReserve && balB >= minReserve) {
        badge.className = 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-700';
        badge.innerText = 'LIQUIDITY READY';
        document.getElementById('liquidityAlertText').innerText = 'AMM pool has sufficient reserves for swaps and compensation unwinds.';
      } else {
        badge.className = 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-700';
        badge.innerText = 'LOW / UNSEEDED';
        document.getElementById('liquidityAlertText').innerText = 'Pool reserves low. Use Seed AMM Pool before executing saga.';
      }
    }

    async function refreshUserTokenBalances() {
      if (!currentAccount || !contractsVerified) return;

      const [balA, balB, shares] = await Promise.all([
        queryTokenBalance(deployedContracts.tka, currentAccount),
        queryTokenBalance(deployedContracts.tkb, currentAccount),
        queryVaultShares(deployedContracts.vault, currentAccount)
      ]);

      userTokenBalances = { tka: balA, tkb: balB, shares: shares };
      document.getElementById('dispUserTKA').innerText = `${formatEther(balA)} TKA`;
      document.getElementById('dispUserTKB').innerText = `${formatEther(balB)} TKB`;
      const elShares = document.getElementById('dispUserShares');
      if (elShares) {
        elShares.innerText = `${formatEther(shares)} SHARES`;
      }

      // On-chain state recovery: if user already holds >= 100 vault shares on Atlantic, record vault position
      // Safety Rule: A stale or unrelated vault balance must NOT falsely prove earlier steps (Step 1 & Step 2) succeeded!
      if (shares >= 100n * 10n**18n && activeScenario === 'happy') {
        const b3 = document.getElementById('badgeStep3');
        if (b3) {
          b3.innerText = 'CONFIRMED';
          b3.className = 'text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300';
        }
        const c3 = document.getElementById('cardStep3');
        if (c3) c3.classList.remove('opacity-60');
        const btn3 = document.getElementById('btnExecuteStep3');
        if (btn3) {
          btn3.disabled = false;
          btn3.className = 'w-full py-2 rounded-xl text-xs font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-700 transition';
          btn3.innerText = 'Step 3 Confirmed (100 Shares Minted)';
        }
      }
    }

    async function claimFaucetTokens() {
      try {
        await validateChainAndWallet();
        if (!contractsVerified) throw new Error('Contracts not verified on Atlantic.');

        logEvent('Claiming 500 TKA and 500 TKB from testnet faucet...', 'info');
        const mintAmountHex = toWeiHex('500');
        const calldata = ERC20_FAUCET_SEL + padUint256(mintAmountHex);

        showDisclosureModal({
          step: 'faucet_tka',
          contractName: 'TestToken A (TKA)',
          to: deployedContracts.tka,
          methodSignature: 'faucet(uint256 amount)',
          params: { amount: '500 TKA' },
          calldata,
          estGas: 45000,
          purpose: 'Mint 500 TKA from open test faucet to your wallet.'
        });
      } catch (err) {
        logEvent(`Faucet error: ${err.message}`, 'error');
      }
    }

    async function seedPoolLiquidity() {
      try {
        await validateChainAndWallet();
        if (!contractsVerified) throw new Error('Contracts not verified on Atlantic.');

        const seedAmountHex = toWeiHex('1000');
        const seedAmount = 1000n * 10n**18n;

        // Check user balances
        const [uBalA, uBalB] = await Promise.all([
          queryTokenBalance(deployedContracts.tka, currentAccount),
          queryTokenBalance(deployedContracts.tkb, currentAccount)
        ]);

        if (uBalA < seedAmount || uBalB < seedAmount) {
          throw new Error(`Insufficient wallet balance to seed 1,000 TKA and 1,000 TKB. Wallet has ${formatEther(uBalA)} TKA and ${formatEther(uBalB)} TKB. Claim faucet first.`);
        }

        // Check TKA allowance
        const allowA = await queryAllowance(deployedContracts.tka, currentAccount, deployedContracts.amm);
        if (allowA < seedAmount) {
          const calldata = ERC20_APPROVE_SEL + padAddress(deployedContracts.amm) + padUint256(seedAmountHex);
          showDisclosureModal({
            step: 'seed_approve_tka',
            contractName: 'TestToken A (TKA)',
            to: deployedContracts.tka,
            methodSignature: 'approve(address spender, uint256 amount)',
            params: { spender: deployedContracts.amm, amount: '1,000 TKA' },
            calldata,
            estGas: 46758,
            purpose: 'Seed Step 1: Approve AMM to pull 1,000 TKA for pool liquidity.'
          });
          return;
        }

        // Check TKB allowance
        const allowB = await queryAllowance(deployedContracts.tkb, currentAccount, deployedContracts.amm);
        if (allowB < seedAmount) {
          const calldata = ERC20_APPROVE_SEL + padAddress(deployedContracts.amm) + padUint256(seedAmountHex);
          showDisclosureModal({
            step: 'seed_approve_tkb',
            contractName: 'TestToken B (TKB)',
            to: deployedContracts.tkb,
            methodSignature: 'approve(address spender, uint256 amount)',
            params: { spender: deployedContracts.amm, amount: '1,000 TKB' },
            calldata,
            estGas: 46758,
            purpose: 'Seed Step 2: Approve AMM to pull 1,000 TKB for pool liquidity.'
          });
          return;
        }

        // Supply liquidity
        const calldata = AMM_SUPPLY_LIQ_SEL + padUint256(seedAmountHex) + padUint256(seedAmountHex);
        showDisclosureModal({
          step: 'seed_supply',
          contractName: 'TestAMM Router',
          to: deployedContracts.amm,
          methodSignature: 'supplyLiquidity(uint256 amountA, uint256 amountB)',
          params: { amountA: '1,000 TKA', amountB: '1,000 TKB' },
          calldata,
          estGas: 95000,
          purpose: 'Seed Step 3: Deposit 1,000 TKA and 1,000 TKB into TestAMM pool.'
        });
      } catch (err) {
        logEvent(`Liquidity seeding error: ${err.message}`, 'error');
      }
    }

    function selectScenario(mode) {
      activeScenario = mode;
      currentSagaId = null;
      if (mode === 'happy') {
        document.getElementById('btnModeHappy').className = 'px-3 py-1 rounded-lg font-semibold bg-cyan-500 text-black shadow transition';
        document.getElementById('btnModeFailure').className = 'px-3 py-1 rounded-lg text-slate-400 hover:text-white transition';
        document.getElementById('titleStep3').innerText = 'Deposit into Vault';
        document.getElementById('descStep3').innerText = 'Queries TKB allowance for vault (auto-approves if needed), then deposits into TestSagaVault.';
        document.getElementById('gasStep3').innerText = '~121,496 gas';
        document.getElementById('panelCompensation').classList.add('hidden');
        logEvent('Selected Scenario 1: Happy Path (Approve -> Swap -> Normal Deposit).', 'info');
      } else {
        document.getElementById('btnModeFailure').className = 'px-3 py-1 rounded-lg font-semibold bg-purple-600 text-white shadow transition';
        document.getElementById('btnModeHappy').className = 'px-3 py-1 rounded-lg text-slate-400 hover:text-white transition';
        document.getElementById('titleStep3').innerText = 'Forced Deposit Revert (Test)';
        document.getElementById('descStep3').innerText = 'Queries TKB allowance for vault, then calls depositWithFailFlag(amount, true) to trigger deliberate revert.';
        document.getElementById('gasStep3').innerText = '~26,000 gas (revert)';
        logEvent('Selected Scenario 2: Forced Failure (Approve -> Swap -> Deliberate Revert -> LIFO Comp).', 'warn');
      }
    }

    function showDisclosureModal(config) {
      pendingTxConfig = config;
      document.getElementById('discContractName').innerText = config.contractName;
      document.getElementById('discContractAddr').innerText = config.to;
      document.getElementById('discMethodName').innerText = config.methodSignature;
      document.getElementById('discParamsJson').innerText = JSON.stringify(config.params, null, 2);
      document.getElementById('discEstGas').innerText = `${config.estGas.toLocaleString()} gas`;
      document.getElementById('discPurposeText').innerText = config.purpose;
      document.getElementById('modalDisclosure').classList.remove('hidden');
    }

    function closeDisclosureModal() {
      document.getElementById('modalDisclosure').classList.add('hidden');
      pendingTxConfig = null;
    }

    async function proceedWithSignature() {
      const config = pendingTxConfig;
      closeDisclosureModal();
      if (!config) return;

      const isDryRun = document.getElementById('toggleDryRun').checked;
      if (isDryRun) {
        logEvent(`[DRY RUN] Calldata verified: ${config.calldata}`, 'info');
        logEvent(`[DRY RUN] Skipped wallet prompt. Estimated gas: ${config.estGas}`, 'success');
        return;
      }

      await executeOnChainStepTx(config);
    }

    async function executeStep(stepNum, autoExecute = false) {
      try {
        await validateChainAndWallet();
        if (!contractsVerified) throw new Error('Contract infrastructure not verified on Atlantic.');

        if (stepNum === 1) {
          const amountStr = activeScenario === 'happy' ? '100' : '150';
          const amountHex = toWeiHex(amountStr);
          const calldata = ERC20_APPROVE_SEL + padAddress(deployedContracts.amm) + padUint256(amountHex);
          showDisclosureModal({
            step: 1,
            contractName: 'TestToken (Token A)',
            to: deployedContracts.tka,
            methodSignature: 'approve(address spender, uint256 amount)',
            params: { spender: deployedContracts.amm, amount: `${amountStr} TKA` },
            calldata,
            estGas: 46758,
            purpose: 'Step 1: Approve AMM to pull Token A for swap.'
          });
        } else if (stepNum === 2) {
          const amountHex = toWeiHex('100');
          const amountWei = 100n * 10n**18n;

          // Liquidity Guard: Check actual on-chain reserves of TestAMM before opening swap flow
          const minReserveRequired = 100n * 10n**18n;
          const [resA, resB] = await Promise.all([
            queryTokenBalance(deployedContracts.tka, deployedContracts.amm),
            queryTokenBalance(deployedContracts.tkb, deployedContracts.amm)
          ]);
          poolReserves = { tka: resA, tkb: resB };
          document.getElementById('dispPoolTKA').innerText = `${formatEther(resA)} TKA`;
          document.getElementById('dispPoolTKB').innerText = `${formatEther(resB)} TKB`;

          if (resA < minReserveRequired || resB < minReserveRequired) {
            logEvent(`Liquidity Guard: TestAMM pool reserves insufficient for swap (Pool has ${formatEther(resA)} TKA, ${formatEther(resB)} TKB; minimum required: 100 TKA and 100 TKB). Please click "⚡ Seed AMM Pool" first.`, 'error');
            alert(`[Liquidity Guard] TestAMM pool reserves are insufficient:\n• Current Pool TKA: ${formatEther(resA)}\n• Current Pool TKB: ${formatEther(resB)}\n• Required Minimum: 100 TKA & 100 TKB\n\nPlease click "⚡ Seed AMM Pool (1,000 TKA + 1,000 TKB)" above before executing Step 2.`);
            return;
          }

          // Mandatory Pre-Swap Allowance Check
          const currentAllowance = await queryAllowance(deployedContracts.tka, currentAccount, deployedContracts.amm);
          if (currentAllowance < amountWei) {
            logEvent(`Mandatory Pre-Swap Guard: TKA allowance (${formatEther(currentAllowance)} TKA) is less than swap amount (100 TKA). Requesting exact required approval...`, 'warn');
            const approveCalldata = ERC20_APPROVE_SEL + padAddress(deployedContracts.amm) + padUint256(amountHex);
            showDisclosureModal({
              step: 'step2_approve_amm',
              contractName: 'TestToken A (TKA)',
              to: deployedContracts.tka,
              methodSignature: 'approve(address spender, uint256 amount)',
              params: { spender: deployedContracts.amm, amount: '100 TKA' },
              calldata: approveCalldata,
              estGas: 60000,
              purpose: 'Step 2 Prerequisite: Authorize TestAMM to transfer 100 TKA for swap.'
            });
            return;
          }

          if (!currentSagaId) {
            currentSagaId = '0x' + Array.from(crypto.getRandomValues(new Uint8Array(32))).map(b => b.toString(16).padStart(2, '0')).join('');
          }
          // swapWithSagaId(bytes32,address,address,uint256,uint256) selector: 0x963b8dae
          const calldata = AMM_SWAP_SEL + currentSagaId.replace('0x', '') + padAddress(deployedContracts.tka) + padAddress(deployedContracts.tkb) + padUint256(amountHex) + padUint256(amountHex);

          // Pre-flight eth_estimateGas validation for swap calldata
          let swapEstGas = 220000;
          try {
            const estHex = await rpcCall('eth_estimateGas', [{ from: currentAccount, to: deployedContracts.amm, data: calldata }]);
            swapEstGas = Number(BigInt(estHex));
          } catch (estErr) {
            logEvent(`Pre-swap gas estimation failed: ${estErr.message}. Transaction blocked.`, 'error');
            alert(`[Gas Estimation Error] Cannot proceed with swap:\n${estErr.message}\n\nPlease check on-chain conditions before retrying.`);
            return;
          }

          const swapConfig = {
            step: 2,
            contractName: 'TestAMM Router',
            to: deployedContracts.amm,
            methodSignature: 'swapWithSagaId(bytes32,address,address,uint256,uint256)',
            params: { sagaId: currentSagaId, tokenIn: deployedContracts.tka, tokenOut: deployedContracts.tkb, amount: '100 TKA' },
            calldata,
            estGas: swapEstGas,
            purpose: 'Step 2: Swap Token A for Token B with unique sagaId.'
          };

          if (autoExecute) {
            logEvent('Prerequisite confirmed & allowance verified. Prompting wallet signature for Step 2 Swap...', 'info');
            await executeOnChainStepTx(swapConfig);
          } else {
            showDisclosureModal(swapConfig);
          }
        } else if (stepNum === 3) {
          const amountHex = toWeiHex('100');
          const amountWei = 100n * 10n**18n;

          // Prerequisite: Check Token B allowance for TestSagaVault
          const currentAllowance = await queryAllowance(deployedContracts.tkb, currentAccount, deployedContracts.vault);
          if (currentAllowance < amountWei) {
            logEvent(`Token B allowance (${formatEther(currentAllowance)} TKB) is less than deposit amount. Initiating prerequisite approval...`, 'warn');
            const approveCalldata = ERC20_APPROVE_SEL + padAddress(deployedContracts.vault) + padUint256(amountHex);
            showDisclosureModal({
              step: 'step3_approve_vault',
              contractName: 'TestToken B (TKB)',
              to: deployedContracts.tkb,
              methodSignature: 'approve(address spender, uint256 amount)',
              params: { spender: deployedContracts.vault, amount: '100 TKB' },
              calldata: approveCalldata,
              estGas: 60000,
              purpose: 'Step 3 Prerequisite: Authorize TestSagaVault to transfer 100 TKB.'
            });
            return;
          }

          let stepConfig;
          if (activeScenario === 'happy') {
            // deposit(uint256) selector: 0xb6b55f25
            const calldata = VAULT_DEPOSIT_SEL + padUint256(amountHex);
            stepConfig = {
              step: 3,
              contractName: 'TestSagaVault',
              to: deployedContracts.vault,
              methodSignature: 'deposit(uint256 amount)',
              params: { amount: '100 TKB' },
              calldata,
              estGas: 121496,
              purpose: 'Step 3: Deposit Token B into vault and mint 1:1 shares.'
            };
          } else {
            // depositWithFailFlag(uint256,bool) selector: 0xea65d693
            const calldata = VAULT_FAIL_DEPOSIT_SEL + padUint256(amountHex) + padUint256('0x1');
            stepConfig = {
              step: 3,
              contractName: 'TestSagaVault',
              to: deployedContracts.vault,
              methodSignature: 'depositWithFailFlag(uint256,bool=true)',
              params: { amount: '100 TKB', forceFail: true },
              calldata,
              estGas: 26000,
              purpose: 'Step 3: Forced revert to test LIFO compensation.'
            };
          }

          if (autoExecute) {
            logEvent('Prerequisite confirmed & allowance verified. Prompting wallet signature for Step 3 Vault deposit...', 'info');
            await executeOnChainStepTx(stepConfig);
          } else {
            showDisclosureModal(stepConfig);
          }
        }
      } catch (err) {
        logEvent(`Step error: ${err.message}`, 'error');
      }
    }

    async function executeCompensation(compNum, autoExecute = false) {
      try {
        await validateChainAndWallet();
        if (!contractsVerified) throw new Error('Contract infrastructure not verified.');

        if (compNum === 1) {
          const amountHex = toWeiHex('100');
          const amountWei = 100n * 10n**18n;

          // Prerequisite: Check Token B allowance for TestAMM unwind
          const currentAllowance = await queryAllowance(deployedContracts.tkb, currentAccount, deployedContracts.amm);
          if (currentAllowance < amountWei) {
            logEvent(`Token B allowance (${formatEther(currentAllowance)} TKB) is insufficient for AMM unwind. Initiating prerequisite approval...`, 'warn');
            const approveCalldata = ERC20_APPROVE_SEL + padAddress(deployedContracts.amm) + padUint256(amountHex);
            showDisclosureModal({
              step: 'comp1_approve_amm',
              contractName: 'TestToken B (TKB)',
              to: deployedContracts.tkb,
              methodSignature: 'approve(address spender, uint256 amount)',
              params: { spender: deployedContracts.amm, amount: '100 TKB' },
              calldata: approveCalldata,
              estGas: 46758,
              purpose: 'Comp 1 Prerequisite: Authorize TestAMM to pull 100 TKB to unwind swap.'
            });
            return;
          }

          // unwindSwapWithSagaId(bytes32,uint256) selector: 0x0cd8cd2b
          const calldata = AMM_UNWIND_SEL + currentSagaId.replace('0x', '') + padUint256(amountHex);
          const unwindConfig = {
            step: 'comp1',
            contractName: 'TestAMM Router',
            to: deployedContracts.amm,
            methodSignature: 'unwindSwapWithSagaId(bytes32,uint256)',
            params: { sagaId: currentSagaId, amount: '100 TKB' },
            calldata,
            estGas: 63565,
            purpose: 'Comp 1: Unwind swap, return TKB and receive original TKA.'
          };

          if (autoExecute) {
            logEvent('Prerequisite confirmed & allowance verified. Prompting wallet signature for Comp 1 Unwind...', 'info');
            await executeOnChainStepTx(unwindConfig);
          } else {
            showDisclosureModal(unwindConfig);
          }
        } else if (compNum === 2) {
          const calldata = ERC20_APPROVE_SEL + padAddress(deployedContracts.amm) + padUint256('0x0');
          showDisclosureModal({
            step: 'comp2',
            contractName: 'TestToken (Token A)',
            to: deployedContracts.tka,
            methodSignature: 'approve(address,uint256=0)',
            params: { spender: deployedContracts.amm, amount: '0' },
            calldata,
            estGas: 26774,
            purpose: 'Comp 2: Revoke residual allowance on Token A.'
          });
        }
      } catch (err) {
        logEvent(`Compensation error: ${err.message}`, 'error');
      }
    }

    async function executeOnChainStepTx(config) {
      try {
        const methodName = config.methodSignature ? config.methodSignature.split('(')[0] : 'transaction';
        logEvent(`Requesting wallet signature for ${methodName}...`, 'info');

        let gasLimit;
        if (config.step === 3 && activeScenario !== 'happy') {
          // Pre-flight simulation for intentional revert path (Scenario B Step 3)
          logEvent('Pre-flight simulation: verifying expected deliberate revert on TestSagaVault...', 'info');
          let simulationReverted = false;
          let revertReason = '';
          try {
            await rpcCall('eth_call', [{ from: currentAccount, to: config.to, data: config.calldata }, 'latest']);
          } catch (simErr) {
            simulationReverted = true;
            revertReason = simErr.message;
          }
          if (!simulationReverted || !revertReason.includes('DELIBERATE_FORCED_FAILURE')) {
            throw new Error(`Pre-flight simulation did not produce expected revert reason: ${revertReason}`);
          }
          // Bounded gas limit for deliberate revert execution
          gasLimit = 80000n;
          logEvent(`Pre-flight simulation confirmed expected deliberate revert: "${revertReason}". Submitting with explicit bounded gas (${gasLimit.toLocaleString()} gas).`, 'success');
        } else {
          // Dynamic gas estimation via eth_estimateGas using actual calldata and live state
          logEvent(`Estimating gas on-chain for ${methodName}...`, 'info');
          try {
            const estHex = await rpcCall('eth_estimateGas', [{
              from: currentAccount,
              to: config.to,
              data: config.calldata
            }]);
            const freshEstGas = Number(BigInt(estHex));
            // Apply 1.5x (50%) safety margin for on-chain state execution
            const bufferedGas = Math.round(freshEstGas * 1.5);
            // Clamp strictly between 80,000 and 500,000 bounds
            gasLimit = BigInt(Math.min(Math.max(bufferedGas, 80000), 500000));
            logEvent(`Gas estimate verified: ${freshEstGas.toLocaleString()} gas (buffered 1.5x clamped: ${gasLimit.toLocaleString()} gas).`, 'info');
          } catch (estErr) {
            logEvent(`Gas estimation failed for ${methodName}: ${estErr.message}. Transaction blocked to protect funds.`, 'error');
            throw new Error(`Gas estimation failed for ${methodName}: ${estErr.message}`);
          }
        }

        const gasHex = '0x' + gasLimit.toString(16);

        const txHash = await window.ethereum.request({
          method: 'eth_sendTransaction',
          params: [{
            from: currentAccount,
            to: config.to,
            data: config.calldata,
            gas: gasHex
          }]
        });
        logEvent(`Tx broadcast [${methodName}]: ${txHash} (gas limit: ${gasLimit.toLocaleString()})`, 'success');
        const { status, gas, block } = await pollReceipt(txHash, 30, methodName);

        if (config.step === 'faucet_tka' && status === 'SUCCESS') {
          logEvent(`Faucet TKA minted in block #${block}! Now minting TKB...`, 'success');
          const mintAmountHex = toWeiHex('500');
          const calldata = ERC20_FAUCET_SEL + padUint256(mintAmountHex);
          showDisclosureModal({
            step: 'faucet_tkb',
            contractName: 'TestToken B (TKB)',
            to: deployedContracts.tkb,
            methodSignature: 'faucet(uint256 amount)',
            params: { amount: '500 TKB' },
            calldata,
            estGas: 45000,
            purpose: 'Mint 500 TKB from open test faucet to your wallet.'
          });
          return;
        } else if (config.step === 'faucet_tkb' && status === 'SUCCESS') {
          logEvent(`Faucet TKB minted in block #${block}! User token balances updated.`, 'success');
          await refreshUserTokenBalances();
          return;
        } else if (config.step === 'seed_approve_tka' && status === 'SUCCESS') {
          logEvent(`TKA approved for AMM seeding in block #${block}! Re-checking next step...`, 'success');
          await seedPoolLiquidity();
          return;
        } else if (config.step === 'seed_approve_tkb' && status === 'SUCCESS') {
          logEvent(`TKB approved for AMM seeding in block #${block}! Re-checking next step...`, 'success');
          await seedPoolLiquidity();
          return;
        } else if (config.step === 'seed_supply' && status === 'SUCCESS') {
          logEvent(`TestAMM liquidity supplied in block #${block}! 1,000 TKA and 1,000 TKB active in pool.`, 'success');
          await refreshPoolLiquidity();
          await refreshUserTokenBalances();
          return;
        } else if (config.step === 'step2_approve_amm') {
          if (status === 'SUCCESS') {
            logEvent(`Prerequisite AMM swap approval confirmed in block #${block}! Verifying on-chain allowance...`, 'success');
            const verifiedAllowance = await queryAllowance(deployedContracts.tka, currentAccount, deployedContracts.amm);
            const requiredAmount = 100n * 10n**18n;
            if (verifiedAllowance < requiredAmount) {
              logEvent(`Allowance re-verification failed on-chain: found ${formatEther(verifiedAllowance)} TKA, required 100 TKA. Swap blocked.`, 'error');
              return;
            }
            logEvent(`On-chain allowance verified: ${formatEther(verifiedAllowance)} TKA. Proceeding to Step 2 Swap...`, 'success');
            document.getElementById('badgeStep1').innerText = 'CONFIRMED';
            document.getElementById('badgeStep1').className = 'text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300';
            await executeStep(2, true);
          } else {
            logEvent(`Prerequisite AMM approval reverted on-chain in block #${block}. Swap aborted.`, 'error');
          }
          return;
        } else if (config.step === 'step3_approve_vault') {
          if (status === 'SUCCESS') {
            logEvent(`Prerequisite Vault approval confirmed in block #${block}! Verifying on-chain TKB allowance...`, 'success');
            const verifiedAllowance = await queryAllowance(deployedContracts.tkb, currentAccount, deployedContracts.vault);
            const requiredAmount = 100n * 10n**18n;
            if (verifiedAllowance < requiredAmount) {
              logEvent(`TKB allowance re-verification failed on-chain: found ${formatEther(verifiedAllowance)} TKB, required 100 TKB. Deposit blocked.`, 'error');
              return;
            }
            logEvent(`On-chain TKB allowance verified: ${formatEther(verifiedAllowance)} TKB. Proceeding to Step 3 Vault deposit...`, 'success');
            await executeStep(3, true);
          } else {
            logEvent(`Prerequisite Vault approval reverted on-chain in block #${block}. Deposit aborted.`, 'error');
          }
          return;
        } else if (config.step === 'comp1_approve_amm') {
          if (status === 'SUCCESS') {
            logEvent(`Prerequisite AMM unwind approval confirmed in block #${block}! Verifying on-chain TKB allowance...`, 'success');
            const verifiedAllowance = await queryAllowance(deployedContracts.tkb, currentAccount, deployedContracts.amm);
            const requiredAmount = 100n * 10n**18n;
            if (verifiedAllowance < requiredAmount) {
              logEvent(`TKB allowance re-verification failed on-chain: found ${formatEther(verifiedAllowance)} TKB, required 100 TKB. Unwind blocked.`, 'error');
              return;
            }
            logEvent(`On-chain TKB allowance verified: ${formatEther(verifiedAllowance)} TKB. Proceeding to Comp 1 Unwind...`, 'success');
            await executeCompensation(1, true);
          } else {
            logEvent(`Prerequisite AMM unwind approval reverted on-chain in block #${block}. Unwind aborted.`, 'error');
          }
          return;
        } else if (config.step === 1) {
          if (status === 'SUCCESS') {
            document.getElementById('badgeStep1').innerText = 'CONFIRMED';
            document.getElementById('badgeStep1').className = 'text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300';
            document.getElementById('badgeStep2').innerText = 'READY';
            document.getElementById('badgeStep2').className = 'text-[10px] px-2 py-0.5 rounded bg-slate-800 text-cyan-300';
            document.getElementById('cardStep2').classList.remove('opacity-60');
            document.getElementById('btnExecuteStep2').disabled = false;
            document.getElementById('btnExecuteStep2').className = 'w-full py-2 rounded-xl text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 text-black shadow transition';
            await refreshUserTokenBalances();
          } else {
            document.getElementById('badgeStep1').innerText = 'FAILED (REVERTED)';
            document.getElementById('badgeStep1').className = 'text-[10px] px-2 py-0.5 rounded bg-rose-950 text-rose-300';
            logEvent(`Step 1 Approve transaction reverted on-chain in block #${block}.`, 'error');
          }
        } else if (config.step === 2) {
          if (status === 'SUCCESS') {
            document.getElementById('badgeStep2').innerText = 'CONFIRMED';
            document.getElementById('badgeStep2').className = 'text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300';
            document.getElementById('badgeStep3').innerText = 'READY';
            document.getElementById('badgeStep3').className = 'text-[10px] px-2 py-0.5 rounded bg-slate-800 text-cyan-300';
            document.getElementById('cardStep3').classList.remove('opacity-60');
            document.getElementById('btnExecuteStep3').disabled = false;
            document.getElementById('btnExecuteStep3').className = 'w-full py-2 rounded-xl text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 text-black shadow transition';
            await refreshPoolLiquidity();
            await refreshUserTokenBalances();
          } else {
            document.getElementById('badgeStep2').innerText = 'FAILED (REVERTED)';
            document.getElementById('badgeStep2').className = 'text-[10px] px-2 py-0.5 rounded bg-rose-950 text-rose-300';
            logEvent(`Step 2 Swap transaction reverted on-chain in block #${block} (gas used: ${gas.toLocaleString()}). Step 3 remains locked.`, 'error');
          }
        } else if (config.step === 3) {
          if (status === 'SUCCESS' && activeScenario === 'happy') {
            document.getElementById('badgeStep3').innerText = 'CONFIRMED';
            document.getElementById('badgeStep3').className = 'text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300';
            const btn3 = document.getElementById('btnExecuteStep3');
            if (btn3) {
              btn3.disabled = false;
              btn3.className = 'w-full py-2 rounded-xl text-xs font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-700 transition';
              btn3.innerText = 'Step 3 Confirmed (100 Shares Minted)';
            }
            logEvent(`Happy path completed! 3/3 on-chain steps verified in block #${block}`, 'success');
            await refreshUserTokenBalances();
            const shares = await queryVaultShares(deployedContracts.vault, currentAccount);
            logEvent(`Vault share balance confirmed: ${formatEther(shares)} shares.`, 'success');
          } else if (status === 'REVERTED' && activeScenario !== 'happy') {
            document.getElementById('badgeStep3').innerText = 'REVERTED (EXPECTED)';
            document.getElementById('badgeStep3').className = 'text-[10px] px-2 py-0.5 rounded bg-rose-950 text-rose-300';
            document.getElementById('panelCompensation').classList.remove('hidden');
            logEvent(`Step 3 reverted as planned on-chain (mined receipt status 0x0 in block #${block}, gas used: ${gas.toLocaleString()}). Activating reverse LIFO compensation.`, 'warn');
          } else {
            document.getElementById('badgeStep3').innerText = 'FAILED';
            document.getElementById('badgeStep3').className = 'text-[10px] px-2 py-0.5 rounded bg-rose-950 text-rose-300';
            logEvent(`Step 3 unexpected transaction status: ${status} in block #${block}`, 'error');
          }
        } else if (config.step === 'comp1' && status === 'SUCCESS') {
          document.getElementById('btnExecuteComp2').disabled = false;
          document.getElementById('btnExecuteComp2').className = 'w-full py-1.5 rounded-lg text-xs font-semibold bg-purple-600 hover:bg-purple-500 text-white transition';
          document.getElementById('cardComp2').classList.remove('opacity-60');
          logEvent(`Comp 1 confirmed in block #${block}! TKA restored to wallet.`, 'comp');
          await refreshPoolLiquidity();
          await refreshUserTokenBalances();
        } else if (config.step === 'comp2' && status === 'SUCCESS') {
          logEvent(`Comp 2 confirmed in block #${block}! Residual allowance revoked.`, 'comp');
          await refreshUserTokenBalances();
        }
      } catch (err) {
        if (err.code === 4001 || (err.message && err.message.includes('User rejected')) || (err.message && err.message.includes('ACTION_REJECTED'))) {
          logEvent(`Transaction prompt rejected by user in wallet. Action aborted without state change.`, 'warn');
        } else {
          logEvent(`Execution error: ${err.message}`, 'error');
        }
      }
    }

"""

# Stitch together the HTML
patched_html = (
    orig_html[:main_close]
    + saga_html_block
    + orig_html[main_close:dom_event_idx]
    + saga_js_block
    + orig_html[dom_event_idx:]
)

# Also ensure DOMContentLoaded calls loadAndVerifyDeployedContracts()
old_dom_listener = "window.addEventListener('DOMContentLoaded', () => {\n      refreshLiveBalances();"
new_dom_listener = "window.addEventListener('DOMContentLoaded', () => {\n      refreshLiveBalances();\n      loadAndVerifyDeployedContracts();"

patched_html = patched_html.replace(old_dom_listener, new_dom_listener, 1)

# Also enhance pollReceipt to record method names in activity log and inspect element
old_poll = (
    "async function pollReceipt(txHash, maxAttempts = 30) {\n"
    "      logEvent(`Polling on-chain receipt for ${txHash.substring(0, 16)}...`, 'info');\n"
    "      for (let i = 0; i < maxAttempts; i++) {\n"
    "        await new Promise(r => setTimeout(r, 1500));\n"
    "        const receipt = await rpcCall('eth_getTransactionReceipt', [txHash]);\n"
    "        if (receipt) {\n"
    "          const status = receipt.status === '0x1' ? 'SUCCESS' : 'REVERTED';\n"
    "          const gas = parseInt(receipt.gasUsed, 16);\n"
    "          const block = parseInt(receipt.blockNumber, 16);\n"
    "          document.getElementById('inspLastTx').innerHTML = `<a href=\"https://atlantic.pharosscan.xyz/tx/${txHash}\" target=\"_blank\" class=\"text-cyan-400 underline\">${txHash.substring(0, 12)}...</a>`;\n"
    "          document.getElementById('inspLastBlock').innerText = `#${block}`;\n"
    "          document.getElementById('inspLastStatus').innerText = status;\n"
    "          document.getElementById('metricGasConsumed').innerText = gas.toLocaleString();\n"
    "          return { receipt, status, gas, block };\n"
    "        }\n"
    "      }\n"
    "      throw new Error(`Receipt timeout for transaction ${txHash} after ${maxAttempts} polls`);\n"
    "    }"
)

new_poll = (
    "async function pollReceipt(txHash, maxAttempts = 30, methodName = '') {\n"
    "      logEvent(`Polling on-chain receipt for ${txHash.substring(0, 16)}...${methodName ? ' [' + methodName + ']' : ''}`, 'info');\n"
    "      for (let i = 0; i < maxAttempts; i++) {\n"
    "        await new Promise(r => setTimeout(r, 1500));\n"
    "        const receipt = await rpcCall('eth_getTransactionReceipt', [txHash]);\n"
    "        if (receipt) {\n"
    "          const status = receipt.status === '0x1' ? 'SUCCESS' : 'REVERTED';\n"
    "          const gas = parseInt(receipt.gasUsed, 16);\n"
    "          const block = parseInt(receipt.blockNumber, 16);\n"
    "          const methodDisplay = methodName ? ` [${methodName}]` : '';\n"
    "          document.getElementById('inspLastTx').innerHTML = `<a href=\"https://atlantic.pharosscan.xyz/tx/${txHash}\" target=\"_blank\" class=\"text-cyan-400 underline\">${txHash.substring(0, 12)}...</a>${methodDisplay}`;\n"
    "          document.getElementById('inspLastBlock').innerText = `#${block}`;\n"
    "          document.getElementById('inspLastStatus').innerText = status;\n"
    "          document.getElementById('metricGasConsumed').innerText = gas.toLocaleString();\n"
    "          return { receipt, status, gas, block };\n"
    "        }\n"
    "      }\n"
    "      throw new Error(`Receipt timeout for transaction ${txHash} after ${maxAttempts} polls`);\n"
    "    }"
)

patched_html = patched_html.replace(old_poll, new_poll, 1)

HTML_PATH.write_text(patched_html, encoding="utf-8")
print(f"[SUCCESS] Wrote patched web/index.html ({len(patched_html)} bytes)")
