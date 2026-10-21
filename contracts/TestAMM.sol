// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

interface IERC20Minimal {
    function transfer(address to, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function allowance(address owner, address spender) external view returns (uint256);
}

/**
 * @title TestAMM
 * @dev MINIMAL TEST INFRASTRUCTURE ONLY — NOT A PRODUCTION DEFI CONTRACT.
 * Implements a deterministic 1:1 test token swap mechanism and isolated, unique-saga-tracked
 * reverse compensation for Pharos Atlantic Testnet saga execution.
 *
 * Security Features:
 * 1. Unique Saga Identifier: Every swap is bound to an immutable `bytes32 sagaId`.
 * 2. Strict Saga Isolation: Compensation credit cannot cross-contaminate or be consumed by other sagas.
 * 3. Partial & Full Unwind Support: Tracks `amountUnwound` per saga record; strictly prevents replay or over-unwinding.
 * 4. Token Attribution: Unwind can only be performed by the saga initiator using the exact pair swapped.
 * 5. Dedicated owner controls pool liquidity withdrawal to prevent third-party liquidity draining.
 * 6. Enforces safe return value checks on all ERC-20 transfers.
 */
contract TestAMM {
    address public immutable owner;
    address public immutable tokenA;
    address public immutable tokenB;

    struct SwapRecord {
        address initiator;
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 amountOut;
        uint256 amountUnwound;
        bool exists;
    }

    // Mapping from unique sagaId -> isolated SwapRecord
    mapping(bytes32 => SwapRecord) public sagaRecords;

    event SwapExecuted(
        bytes32 indexed sagaId,
        address indexed sender,
        address indexed tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOut
    );

    event SwapUnwound(
        bytes32 indexed sagaId,
        address indexed sender,
        address indexed tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOut,
        uint256 remainingUnwindable
    );

    event LiquiditySupplied(address indexed provider, uint256 amountA, uint256 amountB);
    event LiquidityWithdrawn(address indexed owner, uint256 amountA, uint256 amountB);

    modifier onlyOwner() {
        require(msg.sender == owner, "TestAMM: caller is not the owner");
        _;
    }

    constructor(address _tokenA, address _tokenB) {
        require(_tokenA != address(0) && _tokenB != address(0), "TestAMM: invalid token address");
        require(_tokenA != _tokenB, "TestAMM: identical tokens");
        owner = msg.sender;
        tokenA = _tokenA;
        tokenB = _tokenB;
    }

    /**
     * @notice Execute a deterministic 1:1 swap bound to a unique sagaId.
     * @param sagaId Unique identifier for this saga execution (must not have been used previously).
     */
    function swapWithSagaId(
        bytes32 sagaId,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minAmountOut
    ) public returns (uint256 amountOut) {
        require(sagaId != bytes32(0), "TestAMM: empty sagaId");
        require(!sagaRecords[sagaId].exists, "TestAMM: sagaId already used; unique sagaId required");
        require(amountIn > 0, "TestAMM: zero amount in");
        require(
            (tokenIn == tokenA && tokenOut == tokenB) || (tokenIn == tokenB && tokenOut == tokenA),
            "TestAMM: unsupported pair"
        );

        // 1:1 deterministic swap rate
        amountOut = amountIn;
        require(amountOut >= minAmountOut, "TestAMM: slippage exceeded");

        require(
            IERC20Minimal(tokenOut).balanceOf(address(this)) >= amountOut,
            "TestAMM: insufficient pool liquidity"
        );

        // Store immutable saga record
        sagaRecords[sagaId] = SwapRecord({
            initiator: msg.sender,
            tokenIn: tokenIn,
            tokenOut: tokenOut,
            amountIn: amountIn,
            amountOut: amountOut,
            amountUnwound: 0,
            exists: true
        });

        // Pull tokenIn from user
        bool successIn = IERC20Minimal(tokenIn).transferFrom(msg.sender, address(this), amountIn);
        require(successIn, "TestAMM: transferFrom failed");

        // Send tokenOut to user
        bool successOut = IERC20Minimal(tokenOut).transfer(msg.sender, amountOut);
        require(successOut, "TestAMM: transfer failed");

        emit SwapExecuted(sagaId, msg.sender, tokenIn, tokenOut, amountIn, amountOut);
        return amountOut;
    }

    /**
     * @notice Backward-compatible swap without explicit sagaId (auto-generates unique sagaId from parameters and nonce).
     */
    uint256 private _autoNonce;
    function swap(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minAmountOut
    ) external returns (uint256 amountOut) {
        bytes32 autoSagaId = keccak256(abi.encodePacked(msg.sender, block.number, ++_autoNonce, tokenIn, tokenOut, amountIn));
        return swapWithSagaId(autoSagaId, tokenIn, tokenOut, amountIn, minAmountOut);
    }

    /**
     * @notice Reverse compensation function to unwind a swap for a specific saga execution.
     * @param sagaId The exact saga execution being compensated.
     * @param amountToUnwind The amount of output tokens to return to the pool in exchange for original input tokens.
     */
    function unwindSwapWithSagaId(
        bytes32 sagaId,
        uint256 amountToUnwind
    ) public returns (uint256 amountReturned) {
        require(amountToUnwind > 0, "TestAMM: zero unwind amount");

        SwapRecord storage record = sagaRecords[sagaId];
        require(record.exists, "TestAMM: saga record not found");
        require(record.initiator == msg.sender, "TestAMM: unauthorized unwind; caller is not saga initiator");

        uint256 availableToUnwind = record.amountOut - record.amountUnwound;
        require(amountToUnwind <= availableToUnwind, "TestAMM: unwind amount exceeds remaining saga output");

        // Checks-Effects: update unwound state before external transfer
        record.amountUnwound += amountToUnwind;
        amountReturned = amountToUnwind; // 1:1 proportional return

        require(
            IERC20Minimal(record.tokenIn).balanceOf(address(this)) >= amountReturned,
            "TestAMM: insufficient pool liquidity for unwind"
        );

        // Pull tokenOut (the token previously received by user) from user back to AMM
        bool successIn = IERC20Minimal(record.tokenOut).transferFrom(msg.sender, address(this), amountToUnwind);
        require(successIn, "TestAMM: unwind transferFrom failed");

        // Return tokenIn (the original token spent by user) back to user
        bool successOut = IERC20Minimal(record.tokenIn).transfer(msg.sender, amountReturned);
        require(successOut, "TestAMM: unwind transfer failed");

        emit SwapUnwound(
            sagaId,
            msg.sender,
            record.tokenOut,
            record.tokenIn,
            amountToUnwind,
            amountReturned,
            record.amountOut - record.amountUnwound
        );
        return amountReturned;
    }

    /**
     * @notice Provide test liquidity to the pool.
     */
    function supplyLiquidity(uint256 amountA, uint256 amountB) external {
        if (amountA > 0) {
            bool sA = IERC20Minimal(tokenA).transferFrom(msg.sender, address(this), amountA);
            require(sA, "TestAMM: supply tokenA failed");
        }
        if (amountB > 0) {
            bool sB = IERC20Minimal(tokenB).transferFrom(msg.sender, address(this), amountB);
            require(sB, "TestAMM: supply tokenB failed");
        }
        emit LiquiditySupplied(msg.sender, amountA, amountB);
    }

    /**
     * @notice Only the deployer/owner can withdraw supplied liquidity.
     */
    function withdrawLiquidity(uint256 amountA, uint256 amountB) external onlyOwner {
        if (amountA > 0) {
            require(IERC20Minimal(tokenA).balanceOf(address(this)) >= amountA, "TestAMM: insufficient tokenA");
            bool sA = IERC20Minimal(tokenA).transfer(owner, amountA);
            require(sA, "TestAMM: withdraw tokenA failed");
        }
        if (amountB > 0) {
            require(IERC20Minimal(tokenB).balanceOf(address(this)) >= amountB, "TestAMM: insufficient tokenB");
            bool sB = IERC20Minimal(tokenB).transfer(owner, amountB);
            require(sB, "TestAMM: withdraw tokenB failed");
        }
        emit LiquidityWithdrawn(owner, amountA, amountB);
    }
}
