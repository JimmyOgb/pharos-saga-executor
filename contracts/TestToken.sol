// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title TestToken
 * @dev MINIMAL TEST INFRASTRUCTURE ONLY — NOT A PRODUCTION DEFI CONTRACT.
 * Standard ERC-20 implementation with an open faucet function for testnet validation on Pharos Atlantic.
 */
contract TestToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event FaucetMint(address indexed recipient, uint256 amount);

    constructor(string memory _name, string memory _symbol, uint256 _initialSupply) {
        name = _name;
        symbol = _symbol;
        if (_initialSupply > 0) {
            totalSupply = _initialSupply;
            balanceOf[msg.sender] = _initialSupply;
            emit Transfer(address(0), msg.sender, _initialSupply);
        }
    }

    function transfer(address to, uint256 value) external returns (bool) {
        require(to != address(0), "TestToken: transfer to zero address");
        require(balanceOf[msg.sender] >= value, "TestToken: insufficient balance");
        balanceOf[msg.sender] -= value;
        balanceOf[to] += value;
        emit Transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        require(spender != address(0), "TestToken: approve to zero address");
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        require(to != address(0), "TestToken: transfer to zero address");
        require(balanceOf[from] >= value, "TestToken: insufficient balance");
        uint256 currentAllowance = allowance[from][msg.sender];
        require(currentAllowance >= value, "TestToken: insufficient allowance");

        allowance[from][msg.sender] = currentAllowance - value;
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
        return true;
    }

    /**
     * @notice Open test faucet for testnet execution.
     * @param amount The amount of tokens to mint to msg.sender.
     */
    function faucet(uint256 amount) external {
        require(amount <= 1_000_000 * 10**18, "TestToken: faucet request exceeds limit");
        totalSupply += amount;
        balanceOf[msg.sender] += amount;
        emit FaucetMint(msg.sender, amount);
        emit Transfer(address(0), msg.sender, amount);
    }
}
