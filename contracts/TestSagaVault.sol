// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

interface IERC20VaultMinimal {
    function transfer(address to, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/**
 * @title TestSagaVault
 * @dev MINIMAL TEST INFRASTRUCTURE ONLY — NOT A PRODUCTION DEFI CONTRACT.
 * Downstream vault contract for Step 3 of the Pharos 3-step saga.
 *
 * Security Features:
 * 1. Checks-Effects-Interactions: Updates user shares and accounting before external asset transfer.
 * 2. Safe transfer return-value checks.
 * 3. Bounded deliberate failure is strictly per-call via `depositWithFailFlag(amount, forceFail)`:
 *    - Has ZERO persistent storage toggles.
 *    - It cannot be accidentally left enabled.
 *    - Does not affect any subsequent deposits or any other user.
 */
contract TestSagaVault {
    address public immutable asset;
    uint256 public totalDeposited;

    mapping(address => uint256) public userShares;
    mapping(address => uint256) public depositCount;

    event Deposit(address indexed user, uint256 amount, uint256 shares);
    event Withdraw(address indexed user, uint256 amount, uint256 shares);

    constructor(address _asset) {
        require(_asset != address(0), "TestSagaVault: invalid asset address");
        asset = _asset;
    }

    /**
     * @notice Standard Step 3 saga deposit.
     * Always executes normal deposit without failure.
     */
    function deposit(uint256 amount) external returns (uint256 shares) {
        return _processDeposit(msg.sender, amount, false);
    }

    /**
     * @notice Explicit deposit method with failure parameter for direct saga step invocation.
     * @param amount The amount of asset tokens to deposit.
     * @param forceFail If true, triggers an immediate deliberate revert for Scenario B testing.
     *                  Notice this flag is strictly per-call and persists zero state.
     */
    function depositWithFailFlag(uint256 amount, bool forceFail) external returns (uint256 shares) {
        return _processDeposit(msg.sender, amount, forceFail);
    }

    function _processDeposit(address user, uint256 amount, bool shouldFail) internal returns (uint256 shares) {
        require(amount > 0, "TestSagaVault: zero deposit amount");

        // Intentional failure mechanism for Scenario B testing
        if (shouldFail) {
            revert("TestSagaVault: DELIBERATE_FORCED_FAILURE");
        }

        // Checks-Effects-Interactions pattern
        shares = amount; // 1:1 share ratio for test clarity
        userShares[user] += shares;
        totalDeposited += amount;
        depositCount[user] += 1;

        bool success = IERC20VaultMinimal(asset).transferFrom(user, address(this), amount);
        require(success, "TestSagaVault: transferFrom failed");

        emit Deposit(user, amount, shares);
        return shares;
    }

    /**
     * @notice Allows withdrawal of deposited test assets.
     */
    function withdraw(uint256 shares) external returns (uint256 amount) {
        require(shares > 0, "TestSagaVault: zero shares");
        require(userShares[msg.sender] >= shares, "TestSagaVault: insufficient shares");

        amount = shares;
        userShares[msg.sender] -= shares;
        totalDeposited -= amount;

        bool success = IERC20VaultMinimal(asset).transfer(msg.sender, amount);
        require(success, "TestSagaVault: transfer failed");

        emit Withdraw(msg.sender, amount, shares);
        return amount;
    }
}
