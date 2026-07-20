const webhookData = $('Парсинг вебхука').first().json;
const token = 'Bearer ' + $env.PACHCA_TOKEN + '';
const sessionIdRaw = $('get session_id (старт)').first().json.propertyName ?? '';

if (sessionIdRaw.startsWith('завершён:')) {
  try {
    await this.helpers.httpRequest({
      method: 'PATCH',
      url: `https://api.pachca.com/api/shared/v1/messages/${webhookData.message_id}`,
      headers: { 'Authorization': token, 'Content-Type': 'application/json' },
      body: { message: { content: '✅ Тест уже пройден', buttons: [] } }
    });
  } catch(e) {}
  return [];
}

if (!sessionIdRaw) return [];

const sessionRaw = ($('GET сессия (старт)').first().json.propertyName ?? '').replace(/^=/, '');
if (!sessionRaw) return [];
const session = JSON.parse(sessionRaw);

if (['завершён', 'завершен', 'закрыт'].includes(session.статус)) {
  try {
    await this.helpers.httpRequest({
      method: 'PATCH',
      url: `https://api.pachca.com/api/shared/v1/messages/${webhookData.message_id}`,
      headers: { 'Authorization': token, 'Content-Type': 'application/json' },
      body: { message: { content: '✅ Тест уже пройден', buttons: [] } }
    });
  } catch(e) {}
  return [];
}

return [{ json: webhookData }];
