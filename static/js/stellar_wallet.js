(function () {
  "use strict";

  function getCookie(name) {
    const item = document.cookie
      .split(";")
      .map((value) => value.trim())
      .find((value) => value.startsWith(name + "="));
    return item ? decodeURIComponent(item.slice(name.length + 1)) : "";
  }

  function errorMessage(error) {
    if (!error) return "Unknown wallet error.";
    if (typeof error === "string") return error;
    return error.message || error.code || JSON.stringify(error);
  }

  function showStatus(element, message, isError) {
    if (!element) return;
    element.textContent = message;
    element.className = isError
      ? "mt-3 text-sm text-red-700"
      : "mt-3 text-sm text-green-700";
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify(payload || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `Request failed (${response.status}).`);
    }
    return data;
  }

  function bytesToBase64(bytes) {
    let binary = "";
    for (let index = 0; index < bytes.length; index += 1) {
      binary += String.fromCharCode(bytes[index]);
    }
    return window.btoa(binary);
  }

  function normalizeSignature(signature) {
    if (typeof signature === "string") return signature;
    if (signature && signature.type === "Buffer" && Array.isArray(signature.data)) {
      return bytesToBase64(signature.data);
    }
    if (ArrayBuffer.isView(signature)) {
      return bytesToBase64(new Uint8Array(signature.buffer));
    }
    throw new Error("Freighter returned an unsupported signature format.");
  }

  async function getWalletAddress(expectedPassphrase) {
    const api = window.freighterApi;
    if (!api) {
      throw new Error("Freighter could not be loaded. Install or enable the extension.");
    }
    const connection = await api.isConnected();
    if (connection.error) throw new Error(errorMessage(connection.error));
    if (!connection.isConnected) {
      throw new Error("Freighter is not installed or enabled in this browser.");
    }
    const access = await api.requestAccess();
    if (access.error) throw new Error(errorMessage(access.error));
    if (!access.address) throw new Error("Freighter did not return a wallet address.");

    if (expectedPassphrase) {
      const network = await api.getNetworkDetails();
      if (network.error) throw new Error(errorMessage(network.error));
      if (network.networkPassphrase !== expectedPassphrase) {
        throw new Error(
          `Switch Freighter to the required DealSure network (${network.network || "testnet"}).`,
        );
      }
    }
    return access.address;
  }

  async function connectWallet(button) {
    const status = document.getElementById(button.dataset.statusTarget);
    button.disabled = true;
    showStatus(status, "Waiting for Freighter approval...", false);
    try {
      const challenge = await postJson(button.dataset.challengeUrl, {});
      const address = await getWalletAddress(challenge.network_passphrase);
      const signed = await window.freighterApi.signMessage(challenge.message, {
        address,
        networkPassphrase: challenge.network_passphrase,
      });
      if (signed.error) throw new Error(errorMessage(signed.error));
      if (!signed.signedMessage) throw new Error("Freighter did not sign the challenge.");
      await postJson(button.dataset.verifyUrl, {
        address,
        signature: normalizeSignature(signed.signedMessage),
      });
      showStatus(status, "Wallet connected and ownership verified.", false);
      window.setTimeout(() => window.location.reload(), 500);
    } catch (error) {
      showStatus(status, errorMessage(error), true);
      button.disabled = false;
    }
  }

  async function fundEscrow(button) {
    const status = document.getElementById(button.dataset.statusTarget);
    button.disabled = true;
    showStatus(status, "Preparing Stellar transaction...", false);
    try {
      const address = await getWalletAddress();
      const prepared = await postJson(button.dataset.prepareUrl, { address });
      const network = await window.freighterApi.getNetworkDetails();
      if (network.error) throw new Error(errorMessage(network.error));
      if (network.networkPassphrase !== prepared.network_passphrase) {
        throw new Error(`Switch Freighter to ${prepared.network}.`);
      }
      const signed = await window.freighterApi.signTransaction(prepared.xdr, {
        address,
        networkPassphrase: prepared.network_passphrase,
      });
      if (signed.error) throw new Error(errorMessage(signed.error));
      if (!signed.signedTxXdr) throw new Error("Freighter did not sign the transaction.");
      showStatus(status, "Submitting transaction to Stellar...", false);
      const submitted = await postJson(button.dataset.submitUrl, {
        address,
        signed_xdr: signed.signedTxXdr,
      });
      showStatus(status, `Funding confirmed: ${submitted.transaction_hash}`, false);
      window.setTimeout(() => {
        window.location.assign(submitted.redirect_url || window.location.href);
      }, 700);
    } catch (error) {
      showStatus(status, errorMessage(error), true);
      button.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-wallet-connect]").forEach((button) => {
      button.addEventListener("click", () => connectWallet(button));
    });
    document.querySelectorAll("[data-stellar-fund]").forEach((button) => {
      button.addEventListener("click", () => fundEscrow(button));
    });
  });
})();
