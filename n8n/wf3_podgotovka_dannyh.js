const schedule = $('Расписание уведомлений').all();
const sessions = $('Активные сессии').all()
  .filter(s => s.json.session_id && s.json.session_id !== '');

const days = {};
schedule.forEach(row => {
  days[row.json.ключ] = Number(row.json.значение);
});

const reminder1 = days['reminder_day_1'];
const reminder2 = days['reminder_day_2'];
const reminder3 = days['reminder_day_3'];
const autoClose = days['auto_close_day'];
const autoClose2 = days['auto_close_attempt_2_day'] ?? 3;

const now = new Date();

const active = sessions
  .filter(s => ['назначен', 'в процессе'].includes(s.json.статус))
  .map(s => {
    const rawDate = s.json.sent_at || '';
const [datePart, timePart] = rawDate.split(', ');
const [d, m, y] = datePart.split('.');
const sentAt = new Date(`${y}-${m}-${d}T${timePart || '00:00:00'}`);
    const daysPassed = Math.floor((now - sentAt) / (1000 * 60 * 60 * 24));
    const reminderCount = Number(s.json.reminder_count || 0);
    const isAttempt2 = Number(s.json.номер_попытки) === 2;

    const дедлайн = isAttempt2 ? autoClose2 : autoClose;

    let action = null;

    if (daysPassed >= дедлайн) {
      action = 'auto_close';

    } else if (s.json.статус === 'в процессе') {
      action = 'reminder_2';

    } else if (!isAttempt2) {
      if (daysPassed >= reminder3 && reminderCount < 3) action = 'reminder_3';
      else if (daysPassed >= reminder2 && reminderCount < 2) action = 'reminder_2';
      else if (daysPassed >= reminder1 && reminderCount < 1) action = 'reminder_1';
    }

    return {
      ...s.json,
      days_passed: daysPassed,
      action: action
    };
  })
  .filter(s => s.action !== null);

return active.map(s => ({ json: s }));
