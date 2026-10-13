(() => {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
  }
  const form = document.getElementById("billing-form");
  if (!form) return;
  const cart = new Map();
  const container = document.getElementById("bill-lines");
  const hidden = document.getElementById("id_items_json");
  const cartCount = document.getElementById("cart-count");
  const totalCopy = document.getElementById("estimated-total-copy");

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
        if (Number(input.value) <= 0) cart.delete(id);
        else item.quantity = String(Math.min(Number(input.value), Number(item.stock)));
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
  }

  document.body.addEventListener("htmx:responseError", event => {
    if (event.detail.target && event.detail.target.id === "product-results") {
      event.detail.target.textContent = document.getElementById("search-error-message").textContent;
      event.detail.target.classList.add("text-rose-600");
    }
  });

  document.body.addEventListener("click", event => {
    const target = event.target instanceof Element ? event.target : event.target.parentElement;
    const button = target && target.closest("[data-add-product]");
    if (!button) return;
    const id = button.dataset.id;
    const existing = cart.get(id);
    const nextQuantity = (existing ? Number(existing.quantity) : 0) + 1;
    if (nextQuantity > Number(button.dataset.stock)) {
      button.classList.add("add-product-limit");
      window.setTimeout(() => button.classList.remove("add-product-limit"), 500);
      return;
    }
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
  form.addEventListener("submit", event => {
    if (cart.size === 0) {
      event.preventDefault();
      alert(document.getElementById("empty-bill-message").textContent);
    }
  });
})();
