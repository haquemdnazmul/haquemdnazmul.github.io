/* Korean / Bangla strings for the Object Sort Machine simulator (used by ../sim-i18n.js).
   Keys are the exact English text (spaces collapsed). PLC tags, device addresses, units and
   ON/OFF values are deliberately left out so they stay in English. Note: "Stop" is a PLC tag
   in the I/O monitor, so it must never be added as a key. */
window.SIM_I18N = {
  // desktop: bottom-right corner of the 3D view (left of the 390px panel); phones: see CSS in index.html
  barStyle: 'bottom:22px;right:calc(max(16px, env(safe-area-inset-right, 0px)) + 412px)',
  dict: {
    // page / HUD
    'Object Sort Machine Simulator': ['물체 분류 장치 시뮬레이터', 'অবজেক্ট সর্ট মেশিন সিমুলেটর'],
    'Ready': ['준비', 'প্রস্তুত'],
    'E-stop': ['비상정지', 'জরুরি স্টপ'],
    'Paused': ['일시정지', 'বিরতি'],
    'Running': ['운전 중', 'চলছে'],
    'Job done': ['작업 완료', 'কাজ সম্পন্ন'],
    'Load cell · D_PickWeight': ['로드셀 · D_PickWeight', 'লোড সেল · D_PickWeight'],
    'Camera view': ['카메라 시점', 'ক্যামেরা ভিউ'],
    'Iso': ['등각', 'আইসো'],
    'Operator': ['작업자', 'অপারেটর'],
    'Top': ['상면', 'উপর'],
    'Pad': ['패드', 'প্যাড'],
    'Drag to orbit · right-drag to pan · scroll to zoom · Esc = E-stop': ['드래그: 회전 · 우클릭 드래그: 이동 · 스크롤: 확대/축소 · Esc = 비상정지', 'ড্র্যাগ: ঘোরান · রাইট-ড্র্যাগ: সরান · স্ক্রল: জুম · Esc = জরুরি স্টপ'],
    'Loading CAD model…': ['CAD 모델 불러오는 중…', 'CAD মডেল লোড হচ্ছে…'],
    'Building meshes…': ['메시 생성 중…', 'মেশ তৈরি হচ্ছে…'],

    // intro card
    'Built from Object_Sort_Machine.stp. The Mirobot beside the load cell puts each item on the scale, the PLC reads the weight, and the ball-screw gantry runs STEP_MOVE / STEP_PickPlace to store it in the 3×3 grid.':
      ['Object_Sort_Machine.stp로 만든 모델입니다. 로드셀 옆의 Mirobot이 물체를 하나씩 저울에 올리면 PLC가 무게를 읽고, 볼스크류 갠트리가 STEP_MOVE / STEP_PickPlace를 실행해 3×3 그리드에 적재합니다.',
       'Object_Sort_Machine.stp থেকে তৈরি। লোড সেলের পাশের Mirobot প্রতিটি বস্তু স্কেলে রাখে, PLC ওজন পড়ে, আর বল-স্ক্রু গ্যান্ট্রি STEP_MOVE / STEP_PickPlace চালিয়ে সেটি 3×3 গ্রিডে রাখে।'],
    'Mirobot model: WLKATA mirobot_urdf_2 meshes and URDF, used unchanged under the Apache License 2.0 (':
      ['Mirobot 모델: WLKATA mirobot_urdf_2 메시와 URDF를 Apache License 2.0에 따라 변경 없이 사용 (',
       'Mirobot মডেল: WLKATA mirobot_urdf_2 মেশ ও URDF, Apache License 2.0 অনুযায়ী অপরিবর্তিত ব্যবহৃত ('],
    'license': ['라이선스', 'লাইসেন্স'],
    '). The suction cup is added for picking.': ['). 흡착 컵은 픽업용으로 추가했습니다.', ')। পিক করার জন্য সাকশন কাপ যোগ করা হয়েছে।'],

    // operation card
    'Operation': ['운전 조작', 'অপারেশন'],
    'HMI buttons': ['HMI 버튼', 'HMI বোতাম'],
    'Start': ['시작', 'শুরু'],
    'Pause': ['일시정지', 'বিরতি'],
    'Restart': ['재시작', 'পুনরায় শুরু'],
    'Err reset': ['에러 리셋', 'ত্রুটি রিসেট'],
    'Initialize': ['초기화', 'ইনিশিয়ালাইজ'],
    'Sim speed': ['시뮬레이션 속도', 'সিম গতি'],
    'Simulation speed': ['시뮬레이션 속도', 'সিমুলেশন গতি'],
    'Job quantity': ['작업 수량', 'কাজের পরিমাণ'],

    // sorting rule card
    'Sorting rule': ['분류 규칙', 'বাছাই নিয়ম'],
    'by weight': ['무게 기준', 'ওজন অনুযায়ী'],
    'Mode': ['모드', 'মোড'],
    '3 classes, one row each': ['3개 등급, 등급별 1열', '৩টি শ্রেণি, প্রতিটিতে এক সারি'],
    '9 bins, one slot each': ['9개 구간, 구간별 1슬롯', '৯টি বিন, প্রতিটিতে এক স্লট'],
    'Light below (g)': ['경량 상한 (g)', 'হালকা: এর নিচে (g)'],
    'Medium below (g)': ['중량 상한 (g)', 'মাঝারি: এর নিচে (g)'],
    'Anything at or above the medium limit is heavy and goes to slots 7–9. Slots 1–3 are the row nearest the HMI.':
      ['중량 상한 이상은 고중량으로 슬롯 7–9에 적재됩니다. 슬롯 1–3은 HMI에 가장 가까운 열입니다.',
       'মাঝারি সীমা বা তার বেশি ওজন ভারী, যায় স্লট 7–9-এ। স্লট 1–3 হলো HMI-এর সবচেয়ে কাছের সারি।'],
    'Bin 1 starts at (g)': ['구간 1 시작값 (g)', 'বিন 1 শুরু (g)'],
    'Bin width (g)': ['구간 폭 (g)', 'বিনের প্রস্থ (g)'],
    'Slot = bin number. If that slot is taken, the PLC stops with error 10.':
      ['슬롯 = 구간 번호. 해당 슬롯이 차 있으면 PLC가 에러 10으로 정지합니다.',
       'স্লট = বিন নম্বর। সেই স্লট ভরা থাকলে PLC ত্রুটি 10 দিয়ে থামে।'],

    // stored / infeed items
    'Stored items': ['적재 물품', 'সংরক্ষিত বস্তু'],
    'Return stored items to infeed': ['적재 물품을 투입부로 되돌리기', 'সংরক্ষিত বস্তু ইনফিডে ফেরত দিন'],
    'Infeed items': ['투입 물품', 'ইনফিড বস্তু'],
    'true weights, g': ['실제 무게, g', 'প্রকৃত ওজন, g'],
    'Random weights': ['무게 무작위', 'এলোমেলো ওজন'],
    'Refill infeed': ['투입부 다시 채우기', 'ইনফিড পুনরায় ভরুন'],
    'infeed': ['투입부', 'ইনফিড'],
    'on scale': ['저울 위', 'স্কেলে'],
    'robot': ['로봇', 'রোবট'],
    'gantry': ['갠트리', 'গ্যান্ট্রি'],
    'Light': ['경량', 'হালকা'],
    'Medium': ['중량', 'মাঝারি'],
    'Heavy': ['고중량', 'ভারী'],
    'Light: 1–3': ['경량: 1–3', 'হালকা: 1–3'],
    'Medium: 4–6': ['중량: 4–6', 'মাঝারি: 4–6'],
    'Heavy: 7–9': ['고중량: 7–9', 'ভারী: 7–9'],
    'Bin 1 lightest': ['구간 1 최경량', 'বিন 1 সবচেয়ে হালকা'],
    'Bin 9 heaviest': ['구간 9 최중량', 'বিন 9 সবচেয়ে ভারী'],

    // fault injection
    'Fault injection': ['고장 주입', 'ফল্ট ইনজেকশন'],
    'test error handling': ['에러 처리 시험', 'ত্রুটি ব্যবস্থাপনা পরীক্ষা'],
    "Cylinder won't extend (error 7 after T_ErrCylFwd 10 s)": ['실린더 전진 불가 (T_ErrCylFwd 10 s 후 에러 7)', 'সিলিন্ডার সামনে যায় না (T_ErrCylFwd 10 s পরে ত্রুটি 7)'],
    'No vacuum on pick (error 9 after T_ErrSuction 10 s)': ['픽업 시 진공 없음 (T_ErrSuction 10 s 후 에러 9)', 'পিকের সময় ভ্যাকুয়াম নেই (T_ErrSuction 10 s পরে ত্রুটি 9)'],
    'Other errors come from operation: job quantity 0 (1), out of range (2), grid not empty at start (6), no free slot for the class (10, new), infeed empty (11, new).':
      ['그 밖의 에러는 운전 중 발생합니다: 작업 수량 0 (1), 범위 초과 (2), 시작 시 그리드 비어 있지 않음 (6), 해당 등급의 빈 슬롯 없음 (10, 신규), 투입부 비어 있음 (11, 신규).',
       'অন্য ত্রুটিগুলো অপারেশন থেকে আসে: কাজের পরিমাণ 0 (1), সীমার বাইরে (2), শুরুতে গ্রিড খালি নয় (6), শ্রেণির জন্য খালি স্লট নেই (10, নতুন), ইনফিড খালি (11, নতুন)।'],

    // I/O monitor
    'I/O monitor': ['I/O 모니터', 'I/O মনিটর'],
    'XG5000 names': ['XG5000 변수명', 'XG5000 নাম'],
    'Variable': ['변수', 'ভেরিয়েবল'],
    'Device': ['디바이스', 'ডিভাইস'],
    'Value': ['값', 'মান'],
    'NEW': ['신규', 'নতুন'],
    'Rows marked': ['표시', 'চিহ্ন'],
    'are suggested additions for the Mirobot and load cell on free addresses. R_BarcodeDone (M00100) now means "weighing done", so the existing STEP_MOVE ladder runs unchanged.':
      ['가 붙은 행은 Mirobot과 로드셀용으로 빈 주소에 추가를 제안하는 항목입니다. R_BarcodeDone (M00100)은 이제 "계량 완료"를 뜻하므로 기존 STEP_MOVE 래더는 그대로 동작합니다.',
       'দেওয়া সারিগুলো Mirobot ও লোড সেলের জন্য খালি ঠিকানায় প্রস্তাবিত সংযোজন। R_BarcodeDone (M00100) এখন "ওজন মাপা সম্পন্ন" বোঝায়, তাই বিদ্যমান STEP_MOVE ল্যাডার অপরিবর্তিত চলে।'],
    'Stop and errors': ['정지 및 에러', 'স্টপ ও ত্রুটি'],
    'Gantry sequence': ['갠트리 시퀀스', 'গ্যান্ট্রি সিকোয়েন্স'],
    'Cylinder and suction': ['실린더 및 흡착', 'সিলিন্ডার ও সাকশন'],
    'Target slot': ['목표 슬롯', 'লক্ষ্য স্লট'],
    'Slot sensors (BRQP100)': ['슬롯 센서 (BRQP100)', 'স্লট সেন্সর (BRQP100)'],
    'Signal tower': ['시그널 타워', 'সিগন্যাল টাওয়ার'],
    'Mirobot and load cell (new)': ['Mirobot 및 로드셀 (신규)', 'Mirobot ও লোড সেল (নতুন)'],
    'Event log': ['이벤트 로그', 'ইভেন্ট লগ'],

    // error texts (D_ErrCode)
    'Enter the job quantity.': ['작업 수량을 입력하세요.', 'কাজের পরিমাণ লিখুন।'],
    'Job quantity must be between 1 and 9.': ['작업 수량은 1–9 사이여야 합니다.', 'কাজের পরিমাণ 1 থেকে 9-এর মধ্যে হতে হবে।'],
    'The loading area is not empty.': ['적재 영역이 비어 있지 않습니다.', 'লোডিং এলাকা খালি নয়।'],
    'The cylinder did not extend.': ['실린더가 전진하지 않았습니다.', 'সিলিন্ডার সামনে যায়নি।'],
    'The cylinder did not return.': ['실린더가 복귀하지 않았습니다.', 'সিলিন্ডার ফেরেনি।'],
    'The suction device did not turn on.': ['흡착 장치가 켜지지 않았습니다.', 'সাকশন ডিভাইস চালু হয়নি।'],
    'No free slot for this weight class.': ['이 무게 등급의 빈 슬롯이 없습니다.', 'এই ওজন শ্রেণির জন্য খালি স্লট নেই।'],
    'Infeed is empty. Refill it, then press Err reset.': ['투입부가 비었습니다. 채운 뒤 에러 리셋을 누르세요.', 'ইনফিড খালি। ভরে দিয়ে ত্রুটি রিসেট চাপুন।'],

    // event log
    'Job complete (JobDoneSig)': ['작업 완료 (JobDoneSig)', 'কাজ সম্পন্ন (JobDoneSig)'],
    'The CAD model is still loading.': ['CAD 모델을 아직 불러오는 중입니다.', 'CAD মডেল এখনও লোড হচ্ছে।'],
    'Already running.': ['이미 운전 중입니다.', 'ইতিমধ্যে চলছে।'],
    'E-stop is active. Press Initialize first.': ['비상정지 상태입니다. 먼저 초기화를 누르세요.', 'জরুরি স্টপ সক্রিয়। আগে ইনিশিয়ালাইজ চাপুন।'],
    'Clear the error first (Err reset).': ['먼저 에러를 해제하세요 (에러 리셋).', 'আগে ত্রুটি মুছুন (ত্রুটি রিসেট)।'],
    'Paused (R_StopBtn).': ['일시정지 (R_StopBtn).', 'বিরতি (R_StopBtn)।'],
    'Restart.': ['재시작.', 'পুনরায় শুরু।'],
    'EMERGENCY STOP. Press Initialize to recover.': ['비상정지. 복구하려면 초기화를 누르세요.', 'জরুরি স্টপ। পুনরুদ্ধারে ইনিশিয়ালাইজ চাপুন।'],
    'Error reset.': ['에러 리셋.', 'ত্রুটি রিসেট।'],
    'Initialize: homing robot and gantry.': ['초기화: 로봇과 갠트리 원점복귀 중.', 'ইনিশিয়ালাইজ: রোবট ও গ্যান্ট্রি হোমে ফিরছে।'],
    'Ready.': ['준비 완료.', 'প্রস্তুত।'],
    'Grid is already empty.': ['그리드가 이미 비어 있습니다.', 'গ্রিড ইতিমধ্যে খালি।'],
    'Stop the job (Initialize) before refilling.': ['다시 채우기 전에 작업을 정지하세요 (초기화).', 'পুনরায় ভরার আগে কাজ থামান (ইনিশিয়ালাইজ)।'],
    'Infeed refilled with all 9 items.': ['투입부에 물품 9개를 모두 채웠습니다.', 'ইনফিডে ৯টি বস্তুই আবার ভরা হয়েছে।'],
    'New random weights for items in the infeed.': ['투입부 물품에 새 무작위 무게를 적용했습니다.', 'ইনফিডের বস্তুগুলোর নতুন এলোমেলো ওজন।'],
    'CAD model loaded. Set the job quantity and press Start.': ['CAD 모델 로드 완료. 작업 수량을 설정하고 시작을 누르세요.', 'CAD মডেল লোড হয়েছে। কাজের পরিমাণ ঠিক করে শুরু চাপুন।'],

    // HMI screen texture (canvas)
    'OBJECT SORT': ['물체 분류', 'অবজেক্ট সর্ট'],
    'DONE': ['완료', 'সম্পন্ন'],
    'WEIGHT': ['무게', 'ওজন'],
    'ERROR': ['에러', 'ত্রুটি'],
  },
  patterns: [
    [/^STEP_MOVE (\d+) · STEP_Robot (\d+) · Done (\d+)\/(\S+)$/, 'STEP_MOVE $1 · STEP_Robot $2 · 완료 $3/$4', 'STEP_MOVE $1 · STEP_Robot $2 · সম্পন্ন $3/$4'],
    [/^Loading CAD model… ([\d.]+) MB$/, 'CAD 모델 불러오는 중… $1 MB', 'CAD মডেল লোড হচ্ছে… $1 MB'],
    [/^Could not load the CAD model: ([\s\S]*)$/, 'CAD 모델을 불러오지 못했습니다: $1', 'CAD মডেল লোড করা যায়নি: $1'],
    [/^(D_\w+ · D\d+) · slots (\S+)$/, '$1 · 슬롯 $2', '$1 · স্লট $2'],
    [/^(?:slot|SLOT) (\d+)$/, '슬롯 $1', 'স্লট $1'],
    [/^Weight of item (\d+) in grams$/, '물품 $1 무게 (g)', 'বস্তু $1-এর ওজন (গ্রাম)'],
    [/^Error (\d+)$/, '에러 $1', 'ত্রুটি $1'],
    [/^Error (\d+): ([\s\S]+)$/, '에러 $1: $2', 'ত্রুটি $1: $2'],
    [/^Script error: ([\s\S]*)$/, '스크립트 에러: $1', 'স্ক্রিপ্ট ত্রুটি: $1'],
    [/^Stored item in slot (\d+) \((\d+)\/(\d+)\)$/, '슬롯 $1에 적재 완료 ($2/$3)', 'স্লট $1-এ বস্তু রাখা হয়েছে ($2/$3)'],
    [/^Item #(\d+): ([\d.]+) g → (Light|Medium|Heavy), slot (\d+)$/, '물품 #$1: $2 g → $3, 슬롯 $4', 'বস্তু #$1: $2 g → $3, স্লট $4'],
    [/^Item #(\d+): ([\d.]+) g → slot (\d+)$/, '물품 #$1: $2 g → 슬롯 $3', 'বস্তু #$1: $2 g → স্লট $3'],
    [/^Mirobot cannot reach \(([^)]*)\); residual ([\d.]+)$/, 'Mirobot 도달 불가 ($1); 잔차 $2', 'Mirobot পৌঁছাতে পারে না ($1); অবশিষ্ট ত্রুটি $2'],
    [/^Start: job of (\d+) items?$/, '시작: 작업 수량 $1개', 'শুরু: $1টি বস্তুর কাজ'],
    [/^Returned (\d+) stored items? to the infeed\.$/, '적재 물품 $1개를 투입부로 되돌렸습니다.', '$1টি সংরক্ষিত বস্তু ইনফিডে ফেরত গেছে।'],
  ],
};
