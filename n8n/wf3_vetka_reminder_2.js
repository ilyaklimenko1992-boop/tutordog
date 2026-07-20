const sheetData = $('Какое действие?').first().json;
const redisRaw = $input.first().json.propertyName ?? '';
const redisSession = redisRaw ? JSON.parse(redisRaw) : {};
const session = { ...sheetData, ...redisSession };
const status = redisSession.статус || sheetData.статус;

let content, buttons;

if (status === 'в процессе' && session.questions_data) {
  const questionIds = session.question_ids.split(',').map(id => id.trim());
  const idx = Number(session.current_question_index) || 0;
  const q = JSON.parse(session.questions_data)[questionIds[idx]];
  const n = idx + 1;
  const total = session.total_questions || questionIds.length;
  content = `⏰ Ты не закончил срез знаний — давай продолжим.\n\n📋 Вопрос ${n} из ${total}\n\n${q.текст_вопроса}\n\nВыбери один вариант ответа:`;
  buttons = [
    [{ text: `${q.вариант_A}`, data: 'A' }],
    [{ text: `${q.вариант_B}`, data: 'B' }],
    [{ text: `${q.вариант_C}`, data: 'C' }],
    [{ text: `${q.вариант_D}`, data: 'D' }]
  ];
} else {
  content = `📋 Срез знаний всё ещё ждёт тебя. Это важно для твоей аттестации — не откладывай надолго.`;
  buttons = [[{ text: '📋 Начать тест', data: 'start' }]];
}

const response = await this.helpers.httpRequest({
  method: 'POST',
  url: 'https://api.pachca.com/api/shared/v1/messages',
  headers: {
    'Authorization': 'Bearer ' + $env.PACHCA_TOKEN + '',
    'Content-Type': 'application/json'
  },
  body: {
    message: {
      entity_type: 'user',
      entity_id: Number(session.pachca_user_id),
      content: content,
      buttons: buttons
    }
  }
});

const updatedSession = { ...session, статус: status || 'в процессе', last_message_id: response.data.id, reminder_count: 2 };

return [{ json: {
  session_id: session.session_id,
  reminder_count: 2,
  last_message_id: response.data.id,
  updated_session: JSON.stringify(updatedSession)
} }];
