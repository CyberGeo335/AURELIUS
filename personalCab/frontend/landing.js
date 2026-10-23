const dialogs = document.querySelectorAll('dialog');
document.querySelectorAll('[data-dialog]').forEach(button => {
  button.addEventListener('click', () => {
    const dialog = document.getElementById(button.dataset.dialog);
    if (dialog.id === 'application-dialog') {
      document.getElementById('application-content').hidden = false;
      document.getElementById('application-success').hidden = true;
    }
    dialog.showModal();
  });
});
dialogs.forEach(dialog => {
  dialog.querySelectorAll('.dialog-close, [data-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('click', event => {
    const bounds = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
  });
});
document.getElementById('application-form').addEventListener('submit', event => {
  event.preventDefault();
  const phone = event.currentTarget.elements.phone;
  const digits = phone.value.replace(/\D/g, '');
  phone.setCustomValidity(digits.length >= 10 && digits.length <= 15 ? '' : 'Введите от 10 до 15 цифр номера телефона');
  if (!phone.reportValidity()) return;
  document.getElementById('application-content').hidden = true;
  document.getElementById('application-success').hidden = false;
  document.querySelector('#application-success h2').focus();
  event.currentTarget.reset();
});
document.querySelector('input[name="phone"]').addEventListener('input', event => event.target.setCustomValidity(''));
const menuButton = document.querySelector('.menu-button');
menuButton.addEventListener('click', () => {
  const expanded = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!expanded));
  menuButton.setAttribute('aria-label', expanded ? 'Открыть меню' : 'Закрыть меню');
  document.getElementById('mobile-navigation').hidden = expanded;
});
let toastTimer;
document.querySelector('.heart-button').addEventListener('click', event => {
  const button = event.currentTarget;
  const saved = button.getAttribute('aria-pressed') !== 'true';
  button.setAttribute('aria-pressed', String(saved));
  button.setAttribute('aria-label', saved ? 'Убрать из избранного' : 'Добавить в избранное');
  const toast = document.querySelector('.toast');
  toast.textContent = saved ? 'Добавлено в избранное на этой странице' : 'Удалено из избранного';
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 3000);
});
document.getElementById('search-form').addEventListener('submit', event => {
  event.preventDefault();
  const query = document.getElementById('search-input').value.trim().toLocaleLowerCase('ru');
  if (!query) return;
  let firstMatch;
  document.querySelectorAll('.benefit').forEach(card => {
    const matches = card.textContent.toLocaleLowerCase('ru').includes(query);
    card.classList.toggle('search-match', matches);
    if (matches && !firstMatch) firstMatch = card;
  });
  if (firstMatch) {
    document.getElementById('search-dialog').close();
    firstMatch.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' });
  } else {
    document.getElementById('search-result').textContent = 'Ничего не найдено. Попробуйте «ставка», «срок» или «сумма».';
  }
});
