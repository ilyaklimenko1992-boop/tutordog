function decide(sessionIdRaw, session, newLogic) {
  if (sessionIdRaw.startsWith('завершён:')) return 'passed';
  if (!sessionIdRaw) return 'noop';
  if (!session) return 'noop';
  if (newLogic) {
    if (['завершён', 'завершен', 'закрыт'].includes(session.статус)) return 'passed';
    return 'proceed';
  }
  if (session.статус === 'в процессе') return 'stuck';
  if (session.last_message_id && String(session.last_message_id) !== String(999)) return 'stale';
  return 'proceed';
}

const cases = [
  ['завершён-пометка', 'завершён:EMP1_...', null, 'passed', 'passed'],
  ['нет сессии', '', null, 'noop', 'noop'],
  ['назначен, клик по актуальной', 'EMP1_...', { статус: 'назначен', last_message_id: 999 }, 'proceed', 'proceed'],
  ['в процессе (другой день)', 'EMP1_...', { статус: 'в процессе', last_message_id: 111, current_question_index: 2 }, 'proceed', 'stuck'],
  ['без статуса (аномалия)', 'EMP1_...', { статус: null, last_message_id: 111 }, 'proceed', 'stale'],
  ['завершён статус', 'EMP1_...', { статус: 'завершён', last_message_id: 111 }, 'passed', 'stuck'],
  ['клик по устаревшей на назначен', 'EMP1_...', { статус: 'назначен', last_message_id: 111 }, 'proceed', 'stale'],
];

let fail = 0;
for (const [name, sid, sess, expNew, oldBehavior] of cases) {
  const got = decide(sid, sess, true);
  const ok = got === expNew;
  if (!ok) fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'} | ${name} | new=${got} exp=${expNew} | old-was=${decide(sid, sess, false)}`);
}
console.log(fail === 0 ? '\nALL PASS — «в процессе» и «без статуса» теперь резюмируют (proceed), а не тупик' : `\n${fail} FAILED`);
process.exit(fail === 0 ? 0 : 1);
