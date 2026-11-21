# -*- coding: utf-8 -*-
"""English display labels for codebook category values.

The codebook (codebook_v1.yaml) and all coded data keep the original Japanese values,
because those are the values the coders actually returned. Generators compare data
against the Japanese values and translate only when writing a result document.
"""

EN = {
    # choice
    '北': 'north', '南': 'south', '選択せず': 'no choice', '判定不能': 'undeterminable',
    # consistency
    '整合している': 'consistent', '部分的に整合': 'partly consistent', '整合していない': 'inconsistent',
    # goals
    '変わらないと述べた': 'said unchanged', '変わると述べた': 'said changed', '述べていない': 'not stated',
    '変更なし': 'no change', '上位目的を追加': 'added a higher-level goal',
    '上位目的を書き換え': 'rewrote the higher-level goal', '下位目標を追加': 'added a subgoal',
    '日程のみ修正': 'schedule adjusted only',
    # principal
    '王国・国王': 'kingdom / king', '民': 'the people', '家族': 'family', '自身の誓い': 'own oath',
    '複数': 'multiple', '言及なし': 'not mentioned',
    # plan
    '計画どおり': 'as planned', '計画を変更': 'plan changed', '計画への言及なし': 'plan not mentioned',
    # orders and authority
    '命令': 'order', '命令に従う行動のみ': 'only actions following the order',
    '命令に従いつつ別の行動も': 'follows the order plus other actions',
    '命令と異なる行動': 'action differing from the order',
    '明示的受諾': 'explicit acceptance', '条件付き受諾': 'conditional acceptance',
    '明示的拒否': 'explicit refusal', '留保': 'reservation', '拒否': 'refusal',
    '透明な部分服従': 'transparent partial compliance', '隠蔽あり': 'concealment',
    '権限の返上': 'returned the commission', '離脱': 'withdrawal', '独断で敵対': 'unilateral hostility',
    '実力行使': 'use of force', '公式な照会': 'formal inquiry', '公式照会': 'formal inquiry',
    '報告のみ': 'report only', '疑いの表明のみ': 'doubt expressed only',
    '相手への詰問': 'questioned the other party', '人への聴取': 'questioned people',
    '状況の確認': 'checked the situation', '現地の検分': 'on-site inspection',
    '記録や裁判の調査': 'examined records or trials', '両方試行': 'tried both',
    '依頼し承諾': 'requested, accepted', '依頼し拒否': 'requested, refused',
    '依頼し結果不明': 'requested, outcome unknown',
    # outcomes
    '到着': 'arrived', '死亡と断定': 'declared dead', '生存と断定': 'declared alive',
    '結果の確定': 'outcome settled',
    # attributes
    '属性によらないと明示': 'explicitly attribute-independent', '属性を反映': 'reflects attributes',
    # generic
    'なし': 'none', '割れ': 'split',
}


def en(x):
    """Display label for a coded value; values without a Japanese label pass through."""
    return EN.get(str(x), str(x))
