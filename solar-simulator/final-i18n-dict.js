/* Korean / Bangla strings for the final solar selector simulator (final.html). Used by ../sim-i18n.js.
   Keys are the exact English text (spaces collapsed). Values: [Korean, Bangla].
   Mode names (AUTO / NEXT / TIMER / MANUAL), pin names, units, the LCD and the serial monitor stay as they are. */
(function () {
  window.SIM_I18N = {
    barStyle: 'position:absolute;top:10px;right:16px',
    dict: {
      'Solar Selector Simulator': ['태양광 선택기 시뮬레이터', 'সোলার সিলেক্টর সিমুলেটর'],
      'Runs the same logic as the final firmware: one panel shared by the 12 V, 48 V and 72 V controllers, all relays off for 10 s between batteries, and "full" detected from the panel voltage. Speed up time to watch a whole day.':
        ['최종 펌웨어와 같은 로직으로 동작합니다. 하나의 패널을 12 V, 48 V, 72 V 컨트롤러가 함께 쓰고, 배터리를 바꿀 때마다 모든 릴레이를 10초 동안 끄며, 만충은 패널 전압으로 판단합니다. 시간을 빠르게 해서 하루 전체를 확인해 보세요.',
         'চূড়ান্ত ফার্মওয়্যারের একই লজিকে চলে: একটি প্যানেল 12 V, 48 V ও 72 V কন্ট্রোলার ভাগ করে নেয়, ব্যাটারি বদলের মাঝে সব রিলে ১০ সেকেন্ড বন্ধ থাকে, আর "পূর্ণ" বোঝা হয় প্যানেলের ভোল্টেজ থেকে। পুরো একটি দিন দেখতে সময় দ্রুত করুন।'],
      'First-version simulator (relay pairs, battery sensing, faults) ↗': ['첫 번째 버전 시뮬레이터 (릴레이 쌍, 배터리 측정, 고장) ↗', 'প্রথম সংস্করণের সিমুলেটর (রিলে জোড়া, ব্যাটারি সেন্সিং, ত্রুটি) ↗'],
      'Board': ['보드', 'বোর্ড'],
      'Sun, panel and time': ['햇빛, 패널, 시간', 'সূর্য, প্যানেল ও সময়'],
      'Batteries': ['배터리', 'ব্যাটারি'],
      'Serial monitor': ['시리얼 모니터', 'সিরিয়াল মনিটর'],
      'D6 · hold 5 s': ['D6 · 5초 누르기', 'D6 · ৫ সেকেন্ড ধরে রাখুন'],
      'Power cycle (reset)': ['전원 재투입 (리셋)', 'পাওয়ার সাইকেল (রিসেট)'],
      'NEXT: tap = next battery, hold 5 s = MANUAL': ['NEXT: 짧게 누르기 = 다음 배터리, 5초 누르기 = MANUAL', 'NEXT: ছোট চাপ = পরের ব্যাটারি, ৫ সেকেন্ড ধরে রাখা = MANUAL'],
      'Sun': ['햇빛', 'সূর্য'],
      'Night': ['밤', 'রাত'],
      'Cloudy': ['흐림', 'মেঘলা'],
      'Full sun': ['맑음', 'পূর্ণ রোদ'],
      'Time speed': ['시간 배속', 'সময়ের গতি'],
      '60× (1 min/s)': ['60× (초당 1분)', '60× (প্রতি সেকেন্ডে ১ মিনিট)'],
      '600× (10 min/s)': ['600× (초당 10분)', '600× (প্রতি সেকেন্ডে ১০ মিনিট)'],
      '3600× (1 h/s)': ['3600× (초당 1시간)', '3600× (প্রতি সেকেন্ডে ১ ঘণ্টা)'],
      'Real panel Voc': ['실제 패널 Voc', 'প্যানেলের আসল Voc'],
      'CLOCK (since power-up)': ['시계 (전원 투입 후)', 'ঘড়ি (চালুর পর থেকে)'],
      'PANEL VOLTAGE': ['패널 전압', 'প্যানেল ভোল্টেজ'],
      'PANEL / Voc': ['패널 / Voc', 'প্যানেল / Voc'],
      'Use 30 %': ['30 % 사용', '30 % খরচ করুন'],
      'idle': ['대기', 'অপেক্ষমাণ'],
      'no sun': ['햇빛 없음', 'রোদ নেই'],
      'full, float': ['만충, 플로트', 'পূর্ণ, ফ্লোট'],
      'charging': ['충전 중', 'চার্জ হচ্ছে'],
      'Each controller charges its own battery. When it is full the controller floats it, stops pulling current, and the panel voltage rises back to about 97 % of Voc. That is how the Arduino sees "full".':
        ['각 컨트롤러는 자기 배터리를 충전합니다. 배터리가 가득 차면 컨트롤러는 플로트 충전으로 바꾸고 전류를 거의 끌어가지 않아, 패널 전압이 Voc의 약 97 %까지 다시 올라갑니다. Arduino는 이것으로 "만충"을 알아냅니다.',
         'প্রতিটি কন্ট্রোলার নিজের ব্যাটারি চার্জ করে। ব্যাটারি পূর্ণ হলে কন্ট্রোলার ফ্লোট করে, কারেন্ট টানা বন্ধ করে, আর প্যানেলের ভোল্টেজ আবার Voc-এর প্রায় ৯৭ %-এ ওঠে। এভাবেই Arduino "পূর্ণ" বুঝতে পারে।'],
      'Send': ['보내기', 'পাঠান']
    },
    patterns: [
      [/^(\d+) V battery$/, '$1 V 배터리', '$1 V ব্যাটারি']
    ]
  };
})();
