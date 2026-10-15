(() => {
  const themeToggle = document.querySelector("[data-theme-toggle]");
  if (themeToggle) {
    const label = themeToggle.querySelector(".theme-toggle-label");
    const darkLabel = themeToggle.dataset.darkLabel;
    const lightLabel = themeToggle.dataset.lightLabel;
    const updateThemeToggle = () => {
      const isDark = document.documentElement.dataset.theme === "dark";
      const nextLabel = isDark ? lightLabel : darkLabel;
      themeToggle.setAttribute("aria-label", `Switch to ${nextLabel.toLowerCase()}`);
      themeToggle.setAttribute("aria-pressed", String(isDark));
      themeToggle.querySelector(".theme-toggle-icon").textContent = isDark ? "☀" : "☾";
      label.textContent = nextLabel;
      document.querySelector('meta[name="theme-color"]').content = isDark ? "#0b1220" : "#f5f7fb";
    };
    updateThemeToggle();
    themeToggle.addEventListener("click", () => {
      const isDark = document.documentElement.dataset.theme !== "dark";
      if (isDark) document.documentElement.dataset.theme = "dark";
      else delete document.documentElement.dataset.theme;
      try {
        localStorage.setItem("shopsetu-theme", isDark ? "dark" : "light");
      } catch (error) {
        console.warn("ShopSetu could not save the theme preference.", error);
      }
      updateThemeToggle();
    });
  }
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
  }
  const invoiceShareButton = document.querySelector("[data-invoice-share]");
  if (invoiceShareButton) {
    const shareStatus = document.getElementById("invoice-share-status");
    if (
      typeof navigator.share !== "function"
      || typeof navigator.canShare !== "function"
      || typeof File === "undefined"
    ) {
      shareStatus.textContent = invoiceShareButton.dataset.unsupported;
    } else {
      invoiceShareButton.hidden = false;
      invoiceShareButton.disabled = true;
      invoiceShareButton.textContent = invoiceShareButton.dataset.preparing;
      fetch(invoiceShareButton.dataset.pdfUrl, { credentials: "same-origin" })
        .then(response => {
          const contentType = response.headers.get("content-type") || "";
          if (!response.ok || !contentType.toLowerCase().includes("application/pdf")) {
            throw new Error("Invoice PDF could not be loaded.");
          }
          return response.blob();
        })
        .then(blob => {
          const safeNumber = invoiceShareButton.dataset.invoiceNumber.replace(/[^A-Za-z0-9_-]+/g, "-");
          const file = new File([blob], `${safeNumber || "invoice"}.pdf`, { type: "application/pdf" });
          if (!navigator.canShare({ files: [file] })) {
            invoiceShareButton.hidden = true;
            shareStatus.textContent = invoiceShareButton.dataset.unsupported;
            return;
          }
          invoiceShareButton.disabled = false;
          invoiceShareButton.textContent = invoiceShareButton.dataset.ready;
          invoiceShareButton.addEventListener("click", async () => {
            invoiceShareButton.disabled = true;
            try {
              await navigator.share({
                files: [file],
                title: invoiceShareButton.dataset.shareTitle,
                text: invoiceShareButton.dataset.shareText,
              });
              shareStatus.textContent = invoiceShareButton.dataset.shared;
            } catch (error) {
              shareStatus.textContent = error.name === "AbortError"
                ? invoiceShareButton.dataset.cancelled
                : invoiceShareButton.dataset.failed;
            } finally {
              invoiceShareButton.disabled = false;
            }
          });
        })
        .catch(() => {
          invoiceShareButton.hidden = true;
          shareStatus.textContent = invoiceShareButton.dataset.failed;
        });
    }
  }
  const form = document.getElementById("billing-form");
  if (!form) return;
  const cart = new Map();
  const container = document.getElementById("bill-lines");
  const hidden = document.getElementById("id_items_json");
  const cartCount = document.getElementById("cart-count");
  const totalCopy = document.getElementById("estimated-total-copy");

  function syncProductQuantityControls() {
    document.querySelectorAll("[data-product-quantity-controls]").forEach(controls => {
      const card = controls.closest("[data-product-card]");
      const item = card && cart.get(card.dataset.id);
      controls.hidden = !item;
      if (!item) return;
      const input = controls.querySelector("[data-product-quantity]");
      input.value = item.quantity;
      controls.querySelector('[data-quantity-step="1"]').disabled =
        Number(item.quantity) >= Number(item.stock);
    });
  }

  function setProductQuantity(id, quantity) {
    const item = cart.get(id);
    if (!item) return;
    if (quantity <= 0) {
      cart.delete(id);
    } else {
      item.quantity = String(Math.min(quantity, Number(item.stock)));
    }
    render();
  }

  function render() {
    cartCount.textContent = Array.from(cart.values()).reduce((count, item) => count + Number(item.quantity), 0);
    if (cart.size === 0) {
      const empty = document.createElement("p");
      empty.className = "py-4 text-slate-500";
      empty.textContent = document.getElementById("empty-bill-message").textContent;
      container.replaceChildren(empty);
      hidden.value = "[]";
      document.getElementById("estimated-total").textContent = "0.00";
      totalCopy.textContent = "0.00";
      syncProductQuantityControls();
      return;
    }
    const empty = document.getElementById("empty-cart");
    if (empty) empty.remove();
    container.replaceChildren();
    let total = 0;
    for (const [id, item] of cart) {
      const quantity = Number(item.quantity);
      const line = document.createElement("div");
      line.className = "flex flex-wrap items-center justify-between gap-2 py-3";
      const name = document.createElement("strong");
      name.textContent = item.name;
      const amount = document.createElement("span");
      amount.textContent = `₹${(quantity * Number(item.price) * (1 + Number(item.gst) / 100)).toFixed(2)}`;
      const controls = document.createElement("div");
      controls.className = "flex items-center gap-2";
      const input = document.createElement("input");
      input.type = "number";
      input.min = "0.001";
      input.step = "0.001";
      input.value = item.quantity;
      input.className = "w-24 rounded-lg border px-2 py-2";
      input.setAttribute("aria-label", `Quantity for ${item.name}`);
      input.addEventListener("change", () => {
        const requestedQuantity = Number(input.value);
        if (!Number.isFinite(requestedQuantity) || requestedQuantity <= 0) cart.delete(id);
        else item.quantity = String(Math.min(requestedQuantity, Number(item.stock)));
        render();
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "small-button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Remove ${item.name}`);
      remove.addEventListener("click", () => { cart.delete(id); render(); });
      controls.append(input, remove);
      line.append(name, amount, controls);
      container.append(line);
      total += quantity * Number(item.price) * (1 + Number(item.gst) / 100);
    }
    hidden.value = JSON.stringify(Array.from(cart, ([product_id, item]) => ({ product_id, quantity: item.quantity })));
    document.getElementById("estimated-total").textContent = total.toFixed(2);
    totalCopy.textContent = total.toFixed(2);
    syncProductQuantityControls();
  }

  document.body.addEventListener("htmx:responseError", event => {
    if (event.detail.target && event.detail.target.id === "product-results") {
      event.detail.target.textContent = document.getElementById("search-error-message").textContent;
      event.detail.target.classList.add("text-rose-600");
    }
  });

  document.body.addEventListener("click", event => {
    const target = event.target instanceof Element ? event.target : event.target.parentElement;
    const stepButton = target && target.closest("[data-quantity-step]");
    if (stepButton) {
      const card = stepButton.closest("[data-product-card]");
      const item = card && cart.get(card.dataset.id);
      if (!item) return;
      const nextQuantity = Number(item.quantity) + Number(stepButton.dataset.quantityStep);
      setProductQuantity(card.dataset.id, nextQuantity <= 0 ? 0 : nextQuantity);
      return;
    }

    const button = target && target.closest("[data-add-product]");
    if (!button) return;
    const id = button.dataset.id;
    const existing = cart.get(id);
    const nextQuantity = (existing ? Number(existing.quantity) : 0) + 1;
    if (nextQuantity > Number(button.dataset.stock)) return;
    cart.set(id, {
      name: button.dataset.name,
      unit: button.dataset.unit,
      price: button.dataset.price,
      gst: button.dataset.gst,
      stock: button.dataset.stock,
      quantity: String(nextQuantity),
    });
    render();
  });
  document.body.addEventListener("change", event => {
    const input = event.target instanceof HTMLInputElement
      ? event.target.closest("[data-product-quantity]")
      : null;
    if (!input) return;
    const card = input.closest("[data-product-card]");
    const item = card && cart.get(card.dataset.id);
    if (!item) return;
    const requestedQuantity = Number(input.value);
    if (!Number.isFinite(requestedQuantity) || requestedQuantity <= 0) {
      setProductQuantity(card.dataset.id, 0);
      return;
    }
    setProductQuantity(card.dataset.id, requestedQuantity);
  });
  form.addEventListener("submit", event => {
    if (cart.size === 0) {
      event.preventDefault();
      alert(document.getElementById("empty-bill-message").textContent);
    }
  });
})();
