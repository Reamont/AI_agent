"""Русское представление сохранённых стратегий; не новый синтез LLM."""
import argparse
import json
from pathlib import Path
from strategist.store import load

LABELS = {
    'id':'Идентификатор','kind':'Тип варианта','title':'Направление','audience':'Аудитория',
    'job':'Задача пользователя','value':'Механизм ценности','difference':'Отличие',
    'changes':'Изменения продукта','economics':'Экономика','communication':'Коммуникационные последствия',
    'cost':'Затраты','timing':'Плановые сроки','dependencies':'Зависимости','risks':'Риски',
    'reversibility':'Обратимость','objection':'Сильнейшее возражение','falsifier':'Опровергающие данные',
    'viability':'Условия жизнеспособности (ещё требуют проверки)','test':'Необходимая проверка',
    'segment':'Целевой сегмент','context':'Контекст','alternatives':'Альтернативы',
    'direction':'Направление','non_goals':'Осознанные отказы','boundaries':'Границы продукта',
    'capabilities':'Возможности','assumptions':'Допущения','sequence':'Последовательность',
    'situation':'Ситуация выбора','barrier':'Гипотеза барьера','positioning':'Позиционирование',
    'message':'Сообщение','proof':'Основание обещания','channels':'Роль каналов',
    'cta':'Целевое действие','limits':'Ограничения','comprehension_test':'Проверка понимания',
    'hypothesis':'Гипотеза','change':'Изменение','metric':'Основная метрика','baseline':'Исходный уровень',
    'control':'Сравнение','unit':'Единица наблюдения','sample':'Выборка и обоснование',
    'duration':'Срок наблюдения','business_effect':'Минимальный бизнес-эффект',
    'success':'Критерий успеха','failure':'Критерий неуспеха','inconclusive':'Недостаточность данных',
    'guardrails':'Защитные метрики','owner':'Ответственный','action':'Действие по результату',
    'status':'Статус','basis':'Основания','promise_ids':'Связанные обещания',
    'comparison':'Сравнение','sensitivity':'Чувствительность','recommendation':'Рекомендация',
}
STATUS = {'current':'актуально','proposed':'предложено, не утверждено','needs_review':'требует пересмотра',
          'refuted':'опровергнуто','simulated':'учебная симуляция','rejected':'отклонено','withdrawn':'отозвано'}
KINDS = {'status_quo':'сохранить','improve':'улучшить','pivot':'сменить сегмент/модель','close':'закрыть'}


def render(root):
    root=Path(root);s=load(root);st=s.get('strategy')
    if not st:
        raise ValueError('Стратегия отсутствует')
    out=root/'outputs';out.mkdir(exist_ok=True)
    (out/'strategy.json').write_text(json.dumps(st,ensure_ascii=False,indent=2))
    heading=f"Статус: **{STATUS.get(st['status'],st['status'])}**, версия {st.get('version',1)}. Это представление сохранённого результата, не новое исследование."
    lines=['# Четыре стратегических направления','',heading,'']
    for option in st['options']:
        lines+=['## '+option['id']+' — '+option['title'],'']
        for key,value in option.items():
            lines.append(f"- **{LABELS.get(key,key)}:** {KINDS.get(value,value) if key=='kind' else value}")
        lines.append('')
    (out/'options.md').write_text('\n'.join(lines).rstrip()+'\n')
    for section,title in [('product','Продуктовая стратегия'),('communication','Коммуникационная стратегия'),('experiment','План проверки')]:
        lines=['# '+title,'',heading,'']
        lines += [f"**{LABELS.get(k,k)}:** {v}\n" for k,v in st[section].items()]
        if section=='experiment':
            for stage in st.get('experiment_stages',[]):
                lines += ['## '+stage['title'],'']
                lines += [f"**{LABELS.get(k,k)}:** {v}\n" for k,v in stage.items() if k!='title']
        (out/f'{section}.md').write_text('\n'.join(lines).rstrip()+'\n')
    lines=['# Обещания и границы','', '| ID | Обещание → возможность | Основание | Ограничение | Допустимый текст / статус |','|---|---|---|---|---|']
    for p in s['promises'].values():
        lines.append(f"| {p['id']} | {p['message']} → {p['capability']} | {', '.join(p['basis'])} | {p['limitation']} | {p['allowed_wording']} / {STATUS[p['status']]} |")
    (out/'promises.md').write_text('\n'.join(lines).rstrip()+'\n')
    return {'rendered':str(out),'revision':s['revision']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',default='projects/demo')
    print(json.dumps(render(p.parse_args().project),ensure_ascii=False))
