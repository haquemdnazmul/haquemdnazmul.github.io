/* Portfolio translations. Key = the English text on the page (spaces collapsed); value = [Korean, Bangla].
   Text that is the same in every language (product names, model numbers) is simply left out. */
window.PORTFOLIO_I18N = {
  // ---------- page ----------
  'Nazmul Haque Portfolio': ['Nazmul Haque 포트폴리오', 'নাজমুল হক পোর্টফোলিও'],
  'Language': ['언어', 'ভাষা'],

  // ---------- hero ----------
  'Open to automation & robotics roles': ['자동화·로봇 분야 채용 문의 환영', 'অটোমেশন ও রোবোটিক্স পদে কাজের জন্য প্রস্তুত'],
  'Md Nazmul Haque': ['Md Nazmul Haque', 'মোঃ নাজমুল হক'],
  'Automation & Robotics Engineer': ['자동화 · 로봇 엔지니어', 'অটোমেশন ও রোবোটিক্স ইঞ্জিনিয়ার'],
  'I build industrial automation cells end to end: PLC ladder logic and motion control, HMI and SCADA screens, and the Python vision and robot code that ties them together. My projects include a cell that sorts parts by weight using a PLC-driven gantry, a 6-axis robot arm and a 3D depth camera, a conveyor line that sorts parts by length, and a 6-floor elevator controlled by a PLC and an HMI.': [
    '저는 산업 자동화 설비를 처음부터 끝까지 만듭니다. PLC 래더 로직과 모션 제어, HMI·SCADA 화면, 그리고 이 모두를 연결하는 Python 비전·로봇 코드를 직접 개발합니다. 대표 프로젝트로는 PLC 갠트리와 6축 로봇팔, 3D 깊이 카메라로 부품을 무게별로 분류하는 설비, 부품을 길이별로 분류하는 컨베이어 라인, 그리고 PLC와 HMI로 제어하는 6층 승강기가 있습니다.',
    'আমি শুরু থেকে শেষ পর্যন্ত শিল্প অটোমেশন সেল তৈরি করি: PLC ল্যাডার লজিক ও মোশন কন্ট্রোল, HMI ও SCADA স্ক্রিন, এবং এগুলোকে একসাথে যুক্ত করা Python ভিশন ও রোবট কোড। আমার প্রজেক্টগুলোর মধ্যে আছে PLC-চালিত গ্যান্ট্রি, ৬-অক্ষের রোবট আর্ম ও 3D ডেপথ ক্যামেরা দিয়ে ওজন অনুযায়ী যন্ত্রাংশ বাছাইয়ের একটি সেল, দৈর্ঘ্য অনুযায়ী যন্ত্রাংশ বাছাইয়ের একটি কনভেয়র লাইন, এবং PLC ও HMI দিয়ে নিয়ন্ত্রিত একটি ৬ তলার লিফট।'],
  'Weight sorting cell ↓': ['무게 분류 설비 ↓', 'ওজন বাছাই সেল ↓'],
  '3D simulator ↓': ['3D 시뮬레이터 ↓', '3D সিমুলেটর ↓'],
  'Conveyor sorter + 3D ↓': ['컨베이어 분류기 + 3D ↓', 'কনভেয়র সর্টার + 3D ↓'],
  '6-floor elevator + 3D ↓': ['6층 승강기 + 3D ↓', '৬ তলার লিফট + 3D ↓'],

  // ---------- skills ----------
  'Skills': ['보유 기술', 'দক্ষতা'],
  'What I work with': ['다루는 기술', 'যা নিয়ে আমি কাজ করি'],
  'PLC & motion': ['PLC · 모션', 'PLC ও মোশন'],
  'XG5000 ladder': ['XG5000 래더', 'XG5000 ল্যাডার'],
  '2-axis positioning': ['2축 위치 제어', '২-অক্ষ পজিশনিং'],
  'Load-cell module': ['로드셀 모듈', 'লোড-সেল মডিউল'],
  'AC motor control': ['AC 모터 제어', 'AC মোটর নিয়ন্ত্রণ'],
  'Pneumatics': ['공압', 'নিউমেটিক্স'],
  'Sensors': ['센서', 'সেন্সর'],
  'Alarm design': ['알람 설계', 'অ্যালার্ম ডিজাইন'],
  'Robotics & vision': ['로봇 · 비전', 'রোবোটিক্স ও ভিশন'],
  'G-code over serial': ['시리얼 G-code 제어', 'সিরিয়াল G-code নিয়ন্ত্রণ'],
  'Hand-eye calibration': ['핸드-아이 캘리브레이션', 'হ্যান্ড-আই ক্যালিব্রেশন'],
  'Software': ['소프트웨어', 'সফটওয়্যার'],

  // ---------- weight sorting cell ----------
  'Featured project': ['대표 프로젝트', 'প্রধান প্রজেক্ট'],
  'Automated Weight Sorting Cell': ['자동 무게 분류 설비', 'স্বয়ংক্রিয় ওজন বাছাই সেল'],
  'Team': ['팀', 'দল'],
  'Group 1': ['1조', 'গ্রুপ ১'],
  'Group 2': ['2조', 'গ্রুপ ২'],
  'When': ['기간', 'সময়'],
  'Nov 2026': ['2026년 11월', 'নভেম্বর ২০২৬'],
  'Controller': ['컨트롤러', 'কন্ট্রোলার'],
  'Output': ['출력', 'আউটপুট'],
  '9 slots, ordered by weight': ['무게 순으로 9칸에 적재', 'ওজন অনুযায়ী সাজানো ৯টি স্লট'],
  "A working sorting cell that picks blocks, weighs each one on a load cell and places it into one of nine positions in weight order. A 2-axis servo gantry with a pneumatic gripper does the sorting under PLC control. On top of that, a 3D camera finds blocks on the table and a 6-axis robot arm feeds them to the load cell, waiting for the PLC's weight reading before it starts the next pick.": [
    '블록을 집어 로드셀에서 하나씩 무게를 재고, 무게 순서대로 9개 위치 중 한 곳에 놓는 실제 동작하는 분류 설비입니다. 공압 그리퍼가 달린 2축 서보 갠트리가 PLC 제어로 분류를 합니다. 여기에 3D 카메라가 테이블 위의 블록을 찾고, 6축 로봇팔이 블록을 로드셀에 올립니다. 로봇은 PLC의 무게 값을 받은 뒤에 다음 블록을 집습니다.',
    'এটি একটি সচল বাছাই সেল, যা ব্লক তুলে লোড সেলে প্রতিটির ওজন মাপে এবং ওজনের ক্রম অনুযায়ী নয়টি অবস্থানের একটিতে রাখে। নিউমেটিক গ্রিপারসহ একটি ২-অক্ষের সার্ভো গ্যান্ট্রি PLC নিয়ন্ত্রণে বাছাইয়ের কাজ করে। এর সাথে একটি 3D ক্যামেরা টেবিলের ব্লক খুঁজে বের করে, আর একটি ৬-অক্ষের রোবট আর্ম সেগুলো লোড সেলে দেয়। পরের ব্লক তোলার আগে রোবট PLC-এর ওজন রিডিংয়ের জন্য অপেক্ষা করে।'],
  'depth + colour camera': ['깊이 + 컬러 카메라', 'ডেপথ + কালার ক্যামেরা'],
  'Python vision app': ['Python 비전 프로그램', 'Python ভিশন অ্যাপ'],
  'OpenCV · block pose': ['OpenCV · 블록 위치', 'OpenCV · ব্লকের অবস্থান'],
  '6-axis arm': ['6축 로봇팔', '৬-অক্ষের আর্ম'],
  'G-code / serial': ['G-code / 시리얼', 'G-code / সিরিয়াল'],
  'USB serial · RS-485 · Ethernet': ['USB 시리얼 · RS-485 · 이더넷', 'USB সিরিয়াল · RS-485 · ইথারনেট'],
  'Ethernet · FEnet': ['이더넷 · FEnet', 'ইথারনেট · FEnet'],
  'ladder · step sequencer': ['래더 · 스텝 시퀀스', 'ল্যাডার · স্টেপ সিকোয়েন্সার'],
  'Load cell': ['로드셀', 'লোড সেল'],
  'weight → D00400': ['무게 → D00400', 'ওজন → D00400'],
  'places block': ['블록 올림', 'ব্লক রাখে'],
  'analog in': ['아날로그 입력', 'অ্যানালগ ইনপুট'],
  '2-axis gantry': ['2축 갠트리', '২-অক্ষের গ্যান্ট্রি'],
  'servo + pneumatic gripper': ['서보 + 공압 그리퍼', 'সার্ভো + নিউমেটিক গ্রিপার'],
  'sorted output, light → heavy': ['분류 결과: 가벼움 → 무거움', 'বাছাই ফল: হালকা → ভারী'],
  'System diagram: the D455 camera feeds a Python vision program, which drives the Mirobot arm over USB serial. The arm places blocks on the load cell. The XGB PLC reads the load cell, drives the 2-axis gantry into 9 sorted slots, and reports the weight back to Python over RS-485. HMI and SCADA connect to the PLC over Ethernet.': [
    '시스템 구성도: D455 카메라가 Python 비전 프로그램에 영상을 보내고, 프로그램은 USB 시리얼로 Mirobot 로봇팔을 움직입니다. 로봇팔은 블록을 로드셀에 올립니다. XGB PLC는 로드셀 값을 읽어 2축 갠트리로 9칸에 분류하고, 무게를 RS-485로 Python에 보냅니다. HMI와 SCADA는 이더넷으로 PLC에 연결됩니다.',
    'সিস্টেম ডায়াগ্রাম: D455 ক্যামেরা একটি Python ভিশন প্রোগ্রামে তথ্য পাঠায়, যা USB সিরিয়ালের মাধ্যমে Mirobot আর্ম চালায়। আর্ম ব্লকগুলো লোড সেলে রাখে। XGB PLC লোড সেল পড়ে, ২-অক্ষের গ্যান্ট্রি দিয়ে ৯টি স্লটে বাছাই করে এবং RS-485 দিয়ে ওজন Python-এ ফেরত পাঠায়। HMI ও SCADA ইথারনেটের মাধ্যমে PLC-এর সাথে যুক্ত।'],
  'How the parts talk to each other. The dashed link is the weight reading the PLC sends back to the Python program.': [
    '각 장치가 서로 통신하는 방식입니다. 점선은 PLC가 Python 프로그램으로 보내는 무게 값입니다.',
    'যন্ত্রাংশগুলো কীভাবে একে অপরের সাথে যোগাযোগ করে। ড্যাশ দেওয়া লাইনটি হলো PLC থেকে Python প্রোগ্রামে ফেরত পাঠানো ওজনের রিডিং।'],
  'The real weight sorting machine: an aluminium frame with a ball-screw gantry and a suction cup above blue test blocks, the load cell plate in the middle, and a TOP touchscreen HMI with start, stop and emergency stop buttons at the front.': [
    '실제 무게 분류 설비: 알루미늄 프레임에 볼스크루 갠트리와 흡착컵이 파란 시험 블록 위에 있고, 가운데에 로드셀 판, 앞쪽에 시작·정지·비상정지 버튼이 있는 TOP 터치스크린 HMI가 있습니다.',
    'আসল ওজন বাছাই মেশিন: অ্যালুমিনিয়াম ফ্রেমে নীল টেস্ট ব্লকের উপরে বল-স্ক্রু গ্যান্ট্রি ও সাকশন কাপ, মাঝখানে লোড সেল প্লেট, আর সামনে স্টার্ট, স্টপ ও জরুরি স্টপ বোতামসহ একটি TOP টাচস্ক্রিন HMI।'],
  'The real machine: the 2-axis gantry with its suction cup, blue test blocks, the load cell (round plate, centre) and the TOP HMI panel with start, stop and emergency stop.': [
    '실제 설비: 흡착컵이 달린 2축 갠트리, 파란 시험 블록, 로드셀(가운데 원형 판), 그리고 시작·정지·비상정지 버튼이 있는 TOP HMI 패널.',
    'আসল মেশিন: সাকশন কাপসহ ২-অক্ষের গ্যান্ট্রি, নীল টেস্ট ব্লক, লোড সেল (মাঝের গোল প্লেট) এবং স্টার্ট, স্টপ ও জরুরি স্টপসহ TOP HMI প্যানেল।'],
  'PLC sorting logic': ['PLC 분류 로직', 'PLC বাছাই লজিক'],
  'Ladder program in six parts: basic operation, coordinate setup, auto run, manual jog, errors and lamps. Step registers drive homing, pick and place, and sorting. A 9-slot weight table is reordered by swapping entries.': [
    '래더 프로그램은 기본 동작, 좌표 설정, 자동 운전, 수동 조그, 에러, 램프의 6개 부분으로 나뉩니다. 스텝 레지스터가 원점 복귀, 픽앤플레이스, 분류를 순서대로 진행합니다. 9칸 무게 테이블은 값을 서로 바꾸는 방식으로 정렬합니다.',
    'ল্যাডার প্রোগ্রামটি ছয় ভাগে বিভক্ত: বেসিক অপারেশন, কোঅর্ডিনেট সেটআপ, অটো রান, ম্যানুয়াল জগ, এরর ও ল্যাম্প। স্টেপ রেজিস্টার হোমিং, পিক অ্যান্ড প্লেস ও বাছাই পরিচালনা করে। ৯-স্লটের ওজন টেবিলটি মান অদলবদল করে সাজানো হয়।'],
  'XG5000 · XGB · positioning · load-cell module': ['XG5000 · XGB · 위치 제어 · 로드셀 모듈', 'XG5000 · XGB · পজিশনিং · লোড-সেল মডিউল'],
  '3D vision and robot': ['3D 비전과 로봇', '3D ভিশন ও রোবট'],
  "Finds blue blocks by colour and depth. Fits the table plane, then gets each block's centre, size and rotation. Sends the Mirobot raw G-code over USB serial, with no vendor library.": [
    '색상과 깊이 정보로 파란 블록을 찾습니다. 테이블 평면을 맞춘 뒤 각 블록의 중심, 크기, 회전각을 구합니다. 제조사 라이브러리 없이 USB 시리얼로 Mirobot에 G-code를 직접 보냅니다.',
    'রং ও গভীরতা দেখে নীল ব্লক খুঁজে বের করে। টেবিলের সমতল নির্ধারণ করে প্রতিটি ব্লকের কেন্দ্র, আকার ও ঘূর্ণন বের করে। কোনো ভেন্ডর লাইব্রেরি ছাড়াই USB সিরিয়ালে Mirobot-কে সরাসরি G-code পাঠায়।'],
  'Operator app with face login': ['얼굴 인식 로그인 운영 프로그램', 'ফেস লগইনসহ অপারেটর অ্যাপ'],
  'A desktop app with face-recognition sign-in, Admin and Operator roles, English and Korean screens, calibration tools, a run log and a live 3D view of the robot.': [
    '얼굴 인식 로그인, 관리자·작업자 권한, 영어·한국어 화면, 캘리브레이션 도구, 운전 기록, 로봇 실시간 3D 화면을 갖춘 데스크톱 프로그램입니다.',
    'ফেস-রিকগনিশন সাইন-ইন, অ্যাডমিন ও অপারেটর রোল, ইংরেজি ও কোরিয়ান স্ক্রিন, ক্যালিব্রেশন টুল, রান লগ এবং রোবটের লাইভ 3D ভিউসহ একটি ডেস্কটপ অ্যাপ।'],
  'HMI, SCADA and simulators': ['HMI, SCADA, 시뮬레이터', 'HMI, SCADA ও সিমুলেটর'],
  'An HMI panel for the sorter, a CIMON SCADA tag set covering two production lines, and browser-based 3D simulators of the machine packaged as Windows apps.': [
    '분류기용 HMI 화면, 두 생산 라인을 다루는 CIMON SCADA 태그 세트, 그리고 Windows 프로그램으로 만든 브라우저 기반 3D 설비 시뮬레이터입니다.',
    'সর্টারের জন্য একটি HMI প্যানেল, দুটি প্রোডাকশন লাইনের জন্য CIMON SCADA ট্যাগ সেট, এবং Windows অ্যাপ হিসেবে প্যাকেজ করা ব্রাউজার-ভিত্তিক 3D মেশিন সিমুলেটর।'],
  'PLC, Python and SCADA files on GitHub ↗': ['GitHub의 PLC · Python · SCADA 파일 ↗', 'GitHub-এ PLC, Python ও SCADA ফাইল ↗'],

  // ---------- weight sorter simulator ----------
  'Try it in your browser': ['브라우저에서 직접 해 보기', 'ব্রাউজারে চালিয়ে দেখুন'],
  '3D machine simulator': ['3D 설비 시뮬레이터', '3D মেশিন সিমুলেটর'],
  "A 3D model of the sorting machine and the Mirobot arm, built with Three.js from the machine's CAD mesh and the official Mirobot model. Drag to turn the view and scroll to zoom. It runs a full sorting cycle on screen, so anyone can see how the machine works without the hardware. The first load takes a few seconds because the model is about 15 MB.": [
    '설비의 CAD 모델과 Mirobot 공식 모델로 Three.js를 사용해 만든 분류 설비와 로봇팔의 3D 모델입니다. 드래그하면 시점이 돌아가고, 스크롤하면 확대됩니다. 화면에서 전체 분류 과정이 실행되므로 실제 장비 없이도 설비가 어떻게 동작하는지 볼 수 있습니다. 모델 크기가 약 15MB라 처음 불러올 때 몇 초 걸립니다.',
    'মেশিনের CAD মেশ ও অফিসিয়াল Mirobot মডেল থেকে Three.js দিয়ে তৈরি বাছাই মেশিন ও Mirobot আর্মের একটি 3D মডেল। ভিউ ঘোরাতে ড্র্যাগ করুন, জুম করতে স্ক্রল করুন। স্ক্রিনে পুরো বাছাই চক্রটি চলে, তাই হার্ডওয়্যার ছাড়াই যে কেউ মেশিনটি কীভাবে কাজ করে দেখতে পারেন। মডেলটি প্রায় ১৫ MB হওয়ায় প্রথমবার লোড হতে কয়েক সেকেন্ড লাগে।'],
  '3D simulator of the weight sorting machine': ['무게 분류 설비 3D 시뮬레이터', 'ওজন বাছাই মেশিনের 3D সিমুলেটর'],
  'Load the 3D simulator': ['3D 시뮬레이터 불러오기', '3D সিমুলেটর লোড করুন'],
  'Open full screen ↗': ['전체 화면으로 열기 ↗', 'পূর্ণ স্ক্রিনে খুলুন ↗'],

  // ---------- Motion-X Studio ----------
  'The operator app we wrote in Python to run the vision, weighing and robot cell from one window. It links the D455 camera, the PLC load cell (over RS-485) and the WLKATA Mirobot, and shows a live 3D view of the robot.': [
    '비전, 계량, 로봇 설비를 한 화면에서 운영하기 위해 Python으로 만든 운영 프로그램입니다. D455 카메라, PLC 로드셀(RS-485), WLKATA Mirobot을 연결하고, 로봇의 실시간 3D 화면을 보여 줍니다.',
    'ভিশন, ওজন মাপা ও রোবট সেল এক উইন্ডো থেকে চালাতে আমরা Python-এ এই অপারেটর অ্যাপটি লিখেছি। এটি D455 ক্যামেরা, PLC লোড সেল (RS-485-এর মাধ্যমে) ও WLKATA Mirobot-কে যুক্ত করে এবং রোবটের লাইভ 3D ভিউ দেখায়।'],
  'Screen': ['화면', 'স্ক্রিন'],
  'What it does': ['기능', 'কী করে'],
  'Face login': ['얼굴 인식 로그인', 'ফেস লগইন'],
  'Webcam sign-in with OpenCV face recognition. A person is logged in after 5 matching frames, and the app locks itself after 10 minutes without use.': [
    'OpenCV 얼굴 인식으로 웹캠 로그인을 합니다. 5프레임 연속으로 일치하면 로그인되고, 10분 동안 사용하지 않으면 자동으로 잠깁니다.',
    'OpenCV ফেস রিকগনিশন দিয়ে ওয়েবক্যামে সাইন-ইন। পরপর ৫টি ফ্রেম মিললে লগইন হয়, আর ১০ মিনিট ব্যবহার না হলে অ্যাপ নিজে থেকে লক হয়ে যায়।'],
  'Dashboard': ['대시보드', 'ড্যাশবোর্ড'],
  'Live camera view, 3D robot simulator, machine state, load cell weight, session counts and the START / STOP / AUTO controls.': [
    '실시간 카메라 화면, 3D 로봇 시뮬레이터, 설비 상태, 로드셀 무게, 작업 수량, START / STOP / AUTO 버튼.',
    'লাইভ ক্যামেরা ভিউ, 3D রোবট সিমুলেটর, মেশিনের অবস্থা, লোড সেলের ওজন, সেশনের গণনা এবং START / STOP / AUTO কন্ট্রোল।'],
  'Learning': ['학습', 'লার্নিং'],
  'Pick height learned per stack layer. A good pick moves the next one 1 mm higher, a miss 3 mm lower, within set limits.': [
    '적층 단마다 집는 높이를 학습합니다. 성공하면 다음 높이를 1mm 올리고, 실패하면 3mm 내립니다(정해진 범위 안에서).',
    'প্রতিটি স্তূপের স্তরের জন্য তোলার উচ্চতা শেখে। সফল হলে পরেরটি ১ মিমি উপরে, ব্যর্থ হলে ৩ মিমি নিচে—নির্ধারিত সীমার মধ্যে।'],
  'Calibration': ['캘리브레이션', 'ক্যালিব্রেশন'],
  'One-click automatic camera-to-robot calibration. The result is rejected if the error is over 15 mm. Admin only.': [
    '버튼 한 번으로 카메라-로봇 자동 캘리브레이션을 합니다. 오차가 15mm를 넘으면 결과를 버립니다. 관리자 전용.',
    'এক ক্লিকে স্বয়ংক্রিয় ক্যামেরা-থেকে-রোবট ক্যালিব্রেশন। ত্রুটি ১৫ মিমির বেশি হলে ফল বাতিল হয়। শুধু অ্যাডমিনের জন্য।'],
  'Users': ['사용자', 'ব্যবহারকারী'],
  'Add, re-scan or delete face IDs with Admin or Operator roles. The face model retrains itself after every change.': [
    '관리자 또는 작업자 권한으로 얼굴 ID를 추가, 재등록, 삭제합니다. 변경할 때마다 얼굴 모델이 자동으로 다시 학습됩니다.',
    'অ্যাডমিন বা অপারেটর রোলসহ ফেস আইডি যোগ, পুনরায় স্ক্যান বা মুছে ফেলা যায়। প্রতিটি পরিবর্তনের পর ফেস মডেল নিজে থেকে আবার প্রশিক্ষিত হয়।'],
  'Log': ['기록', 'লগ'],
  'Machine log and access log.': ['설비 기록과 접속 기록.', 'মেশিন লগ ও অ্যাক্সেস লগ।'],
  'Live 3D robot': ['실시간 3D 로봇', 'লাইভ 3D রোবট'],
  'With the real robot, the 3D arm follows the joint angles read from every status reply. In dry-run mode every robot command is turned into joint angles and animated, so a whole run can be checked without moving the robot.': [
    '실제 로봇과 연결되면 3D 로봇팔이 상태 응답에서 읽은 관절 각도를 그대로 따라 움직입니다. 드라이런 모드에서는 모든 로봇 명령을 관절 각도로 바꿔 애니메이션으로 보여 주므로, 로봇을 움직이지 않고도 전체 작업을 확인할 수 있습니다.',
    'আসল রোবটের সাথে, 3D আর্মটি প্রতিটি স্ট্যাটাস উত্তর থেকে পড়া জয়েন্ট অ্যাঙ্গেল অনুসরণ করে। ড্রাই-রান মোডে প্রতিটি রোবট কমান্ড জয়েন্ট অ্যাঙ্গেলে রূপান্তর করে অ্যানিমেট করা হয়, তাই রোবট না নড়িয়েই পুরো কাজ যাচাই করা যায়।'],
  'Python · NumPy · robot kinematics': ['Python · NumPy · 로봇 기구학', 'Python · NumPy · রোবট কাইনেমেটিক্স'],
  'Pick height per block': ['블록별 집는 높이', 'প্রতি ব্লকে তোলার উচ্চতা'],
  'Each block is picked at its own height: 12.0 + 1.05 × the height the camera measures. The rule was fitted to heights taught in WLKATA Studio and checked on the real robot.': [
    '블록마다 자기 높이에서 집습니다: 12.0 + 1.05 × 카메라가 잰 높이. 이 식은 WLKATA Studio에서 티칭한 높이에 맞춰 만들었고, 실제 로봇으로 검증했습니다.',
    'প্রতিটি ব্লক তার নিজের উচ্চতায় তোলা হয়: ১২.০ + ১.০৫ × ক্যামেরার মাপা উচ্চতা। নিয়মটি WLKATA Studio-তে শেখানো উচ্চতার সাথে মিলিয়ে তৈরি এবং আসল রোবটে যাচাই করা হয়েছে।'],
  'Depth camera · fitted model': ['깊이 카메라 · 보정 모델', 'ডেপথ ক্যামেরা · ফিটেড মডেল'],
  'English and Korean': ['영어와 한국어', 'ইংরেজি ও কোরিয়ান'],
  'One button switches the whole app between English and Korean, and the choice is remembered. A status bar shows lights for the robot, camera, PLC and face model.': [
    '버튼 하나로 프로그램 전체를 영어와 한국어로 바꾸고, 선택한 언어를 기억합니다. 상태 표시줄에는 로봇, 카메라, PLC, 얼굴 모델의 상태 표시등이 있습니다.',
    'একটি বোতামে পুরো অ্যাপ ইংরেজি ও কোরিয়ানের মধ্যে বদলায়, এবং পছন্দটি মনে রাখে। স্ট্যাটাস বারে রোবট, ক্যামেরা, PLC ও ফেস মডেলের সংকেত বাতি দেখায়।'],
  'Source code on GitHub ↗': ['GitHub의 소스 코드 ↗', 'GitHub-এ সোর্স কোড ↗'],

  // ---------- problems solved ----------
  'Engineering details': ['기술 상세', 'ইঞ্জিনিয়ারিং বিবরণ'],
  'Problems I solved': ['해결한 문제들', 'যে সমস্যাগুলো সমাধান করেছি'],
  'Camera-to-robot calibration': ['카메라-로봇 캘리브레이션', 'ক্যামেরা-থেকে-রোবট ক্যালিব্রেশন'],
  "The arm visits 36 points at three heights while the camera tracks a marker on the tool. OpenCV's solvePnPRansac then works out exactly where the camera is relative to the robot, with no manual measuring.": [
    '로봇팔이 세 높이에서 36개 지점을 돌고, 그동안 카메라가 툴의 마커를 추적합니다. 그런 다음 OpenCV의 solvePnPRansac이 로봇 기준 카메라 위치를 정확히 계산하므로 수동 측정이 필요 없습니다.',
    'ক্যামেরা টুলের একটি মার্কার অনুসরণ করার সময় আর্মটি তিনটি উচ্চতায় ৩৬টি বিন্দুতে যায়। এরপর OpenCV-এর solvePnPRansac রোবটের তুলনায় ক্যামেরার সঠিক অবস্থান বের করে, কোনো হাতে মাপজোখ ছাড়াই।'],
  'Weight as feedback': ['무게를 피드백으로 활용', 'ফিডব্যাক হিসেবে ওজন'],
  'If no weight appears after a place, the block was missed, so the next pick goes 3 mm lower. To find a block by touch, the arm lowers in 1 mm steps while watching the load cell.': [
    '내려놓은 뒤 무게가 잡히지 않으면 블록을 놓친 것이므로 다음에는 3mm 더 낮게 집습니다. 블록을 촉감으로 찾을 때는 로드셀 값을 보면서 1mm씩 내려갑니다.',
    'রাখার পর ওজন না এলে বুঝতে হবে ব্লকটি ধরা যায়নি, তাই পরের বার ৩ মিমি নিচে তোলা হয়। স্পর্শে ব্লক খুঁজতে আর্মটি লোড সেল দেখতে দেখতে ১ মিমি করে নামে।'],
  'Talking to the PLC directly': ['PLC와 직접 통신', 'সরাসরি PLC-এর সাথে যোগাযোগ'],
  "I wrote my own client for LS's XGT Cnet protocol over RS-485, so Python can read the weight register in real time. A SCADA tag generator builds 182 tags with alarms for two PLCs over FEnet.": [
    'RS-485용 LS XGT Cnet 프로토콜 클라이언트를 직접 작성해 Python이 무게 레지스터를 실시간으로 읽게 했습니다. SCADA 태그 생성기는 FEnet으로 연결된 PLC 두 대의 태그 182개와 알람을 만듭니다.',
    'RS-485-এর উপর LS-এর XGT Cnet প্রোটোকলের জন্য আমি নিজের ক্লায়েন্ট লিখেছি, যাতে Python রিয়েল টাইমে ওজনের রেজিস্টার পড়তে পারে। একটি SCADA ট্যাগ জেনারেটর FEnet-এর মাধ্যমে দুটি PLC-এর জন্য অ্যালার্মসহ ১৮২টি ট্যাগ তৈরি করে।'],
  'Reliable on the shop floor': ['현장에서도 안정적', 'কারখানায় নির্ভরযোগ্য'],
  'COM ports are found automatically by USB ID, and the serial link reopens itself if the RS-485 adapter drops out.': [
    'COM 포트를 USB ID로 자동으로 찾고, RS-485 어댑터 연결이 끊기면 시리얼 통신을 스스로 다시 엽니다.',
    'USB আইডি দিয়ে COM পোর্ট স্বয়ংক্রিয়ভাবে খুঁজে নেয়, আর RS-485 অ্যাডাপ্টার বিচ্ছিন্ন হলে সিরিয়াল সংযোগ নিজে থেকে আবার চালু হয়।'],
  'Easy to demo': ['쉬운 시연', 'সহজে প্রদর্শনযোগ্য'],
  'The 3D simulators are bundled into Windows .exe files that run with no internet connection, so anyone can try the machine without the hardware.': [
    '3D 시뮬레이터를 인터넷 없이 실행되는 Windows .exe 파일로 만들어, 누구나 실제 장비 없이 설비를 체험할 수 있습니다.',
    '3D সিমুলেটরগুলো ইন্টারনেট ছাড়াই চলা Windows .exe ফাইলে প্যাকেজ করা, তাই হার্ডওয়্যার ছাড়াই যে কেউ মেশিনটি চালিয়ে দেখতে পারেন।'],

  // ---------- hardware ----------
  'Hardware list': ['하드웨어 목록', 'হার্ডওয়্যার তালিকা'],
  'Hardware used': ['사용한 하드웨어', 'ব্যবহৃত হার্ডওয়্যার'],
  'Component': ['구성 요소', 'উপাদান'],
  'Model': ['모델', 'মডেল'],
  'Role': ['역할', 'ভূমিকা'],
  'Sequencing, motion, weighing': ['시퀀스, 모션, 계량', 'সিকোয়েন্সিং, মোশন, ওজন মাপা'],
  'Robot arm': ['로봇팔', 'রোবট আর্ম'],
  'WLKATA Mirobot (6-axis)': ['WLKATA Mirobot (6축)', 'WLKATA Mirobot (৬-অক্ষ)'],
  'Picks blocks and places them on the load cell': ['블록을 집어 로드셀에 올림', 'ব্লক তুলে লোড সেলে রাখে'],
  '3D camera': ['3D 카메라', '3D ক্যামেরা'],
  'Finds blocks and their position': ['블록과 위치를 찾음', 'ব্লক ও তার অবস্থান খুঁজে বের করে'],
  'Gantry': ['갠트리', 'গ্যান্ট্রি'],
  '2-axis servo, pneumatic gripper': ['2축 서보, 공압 그리퍼', '২-অক্ষের সার্ভো, নিউমেটিক গ্রিপার'],
  'Moves blocks into the 9 sorted slots': ['블록을 9개 분류 칸으로 옮김', 'ব্লকগুলো ৯টি বাছাই স্লটে সরায়'],
  'Weighing': ['계량', 'ওজন মাপা'],
  'Load cell + PLC input module': ['로드셀 + PLC 입력 모듈', 'লোড সেল + PLC ইনপুট মডিউল'],
  'Weight with zero, span and 2-point calibration': ['영점·스팬·2점 보정으로 무게 측정', 'জিরো, স্প্যান ও ২-পয়েন্ট ক্যালিব্রেশনসহ ওজন'],
  'Links': ['통신', 'সংযোগ'],
  'Robot · PLC to PC · PLC to HMI and SCADA': ['로봇 · PLC↔PC · PLC↔HMI·SCADA', 'রোবট · PLC থেকে PC · PLC থেকে HMI ও SCADA'],

  // ---------- conveyor ----------
  'Project': ['프로젝트', 'প্রজেক্ট'],
  'Conveyor Sorter for Three Part Lengths': ['컨베이어 길이별 3종 분류기', 'তিন দৈর্ঘ্যের যন্ত্রাংশের কনভেয়র সর্টার'],
  'Aug 25 – Oct 2, 2026': ['2026년 8월 25일 – 10월 2일', '২৫ আগস্ট – ২ অক্টোবর, ২০২৬'],
  'Parts': ['대상', 'যন্ত্রাংশ'],
  '35 / 55 / 85 mm blocks': ['35 / 55 / 85mm 블록', '৩৫ / ৫৫ / ৮৫ মিমি ব্লক'],
  'Two conveyors carry 3D-printed blocks past a row of three sensors that measure each block\'s length. Pneumatic cylinders then push each block into the right bin for small, medium or large. The line runs from a touchscreen HMI. Optionally, a camera and robot arm can load the blocks onto the belt.': [
    '두 대의 컨베이어가 3D 프린팅 블록을 세 개의 센서 앞으로 운반하고, 센서가 블록의 길이를 잽니다. 그다음 공압 실린더가 블록을 소형·중형·대형 상자로 밀어 넣습니다. 라인은 터치스크린 HMI로 운전합니다. 필요하면 카메라와 로봇팔이 블록을 벨트에 올릴 수도 있습니다.',
    'দুটি কনভেয়র 3D-প্রিন্টেড ব্লকগুলোকে তিনটি সেন্সরের সারির পাশ দিয়ে নিয়ে যায়, যা প্রতিটি ব্লকের দৈর্ঘ্য মাপে। তারপর নিউমেটিক সিলিন্ডার প্রতিটি ব্লককে ছোট, মাঝারি বা বড় বাক্সে ঠেলে দেয়। লাইনটি একটি টাচস্ক্রিন HMI থেকে চালানো হয়। চাইলে একটি ক্যামেরা ও রোবট আর্ম বেল্টে ব্লক তুলে দিতে পারে।'],
  'Line layout: blocks enter conveyor 1, pass three length sensors, transfer to conveyor 2, and are pushed by pneumatic cylinders into small, medium and large bins.': [
    '라인 배치: 블록이 컨베이어 1로 들어와 길이 센서 세 개를 지나고, 컨베이어 2로 넘어간 뒤 공압 실린더에 밀려 소형·중형·대형 상자로 들어갑니다.',
    'লাইনের বিন্যাস: ব্লক কনভেয়র ১-এ ঢোকে, তিনটি দৈর্ঘ্য সেন্সর পার হয়, কনভেয়র ২-এ যায়, এবং নিউমেটিক সিলিন্ডার সেগুলোকে ছোট, মাঝারি ও বড় বাক্সে ঠেলে দেয়।'],
  'conveyor 1': ['컨베이어 1', 'কনভেয়র ১'],
  'conveyor 2': ['컨베이어 2', 'কনভেয়র ২'],
  'length sensors ×3': ['길이 센서 ×3', 'দৈর্ঘ্য সেন্সর ×৩'],
  'step transfer': ['단차 승계', 'স্টেপ ট্রান্সফার'],
  'pneumatic pushers': ['공압 푸셔', 'নিউমেটিক পুশার'],
  '3D simulator of the conveyor length sorter': ['컨베이어 길이 분류기 3D 시뮬레이터', 'কনভেয়র দৈর্ঘ্য সর্টারের 3D সিমুলেটর'],
  'Load the 3D conveyor simulator': ['3D 컨베이어 시뮬레이터 불러오기', '3D কনভেয়র সিমুলেটর লোড করুন'],
  "Built from the line's STEP assembly. It runs the PLC logic with the team's real variable names: length measuring, FIFO tracking, the RUN / DRAIN / FAULT / RESET states and the alarm words. The fault-injection panel lets you break a sensor or jam a cylinder to watch the error system respond.": [
    '라인의 STEP 어셈블리로 만들었습니다. 팀의 실제 변수 이름으로 PLC 로직을 실행합니다: 길이 측정, FIFO 추적, RUN / DRAIN / FAULT / RESET 상태, 알람 워드. 고장 주입 패널에서 센서를 고장 내거나 실린더를 막아 에러 시스템이 어떻게 반응하는지 볼 수 있습니다.',
    'লাইনের STEP অ্যাসেম্বলি থেকে তৈরি। এটি দলের আসল ভেরিয়েবল নাম দিয়ে PLC লজিক চালায়: দৈর্ঘ্য মাপা, FIFO ট্র্যাকিং, RUN / DRAIN / FAULT / RESET অবস্থা এবং অ্যালার্ম ওয়ার্ড। ফল্ট-ইনজেকশন প্যানেলে একটি সেন্সর নষ্ট করে বা সিলিন্ডার আটকে দিয়ে এরর সিস্টেম কীভাবে সাড়া দেয় দেখতে পারেন।'],
  'Tracking parts without extra hardware': ['추가 장비 없는 부품 추적', 'বাড়তি হার্ডওয়্যার ছাড়া যন্ত্রাংশ ট্র্যাকিং'],
  'When a block is measured, its expected arrival time at the bin is queued (FIFO), based on a 32-bit running time count. Several blocks can be on the belt at once, and no tracking hardware was bought. A block is pushed only when the arrival sensor and the queue agree.': [
    '블록을 측정하면 32비트 누적 가동 시간을 기준으로 상자 도착 예정 시간을 대기열(FIFO)에 넣습니다. 여러 블록이 동시에 벨트 위에 있을 수 있고, 추적용 장비를 따로 사지 않았습니다. 도착 센서와 대기열이 일치할 때만 블록을 밀어냅니다.',
    'একটি ব্লক মাপা হলে, ৩২-বিটের চলমান সময় গণনার ভিত্তিতে বাক্সে তার পৌঁছানোর প্রত্যাশিত সময় সারিতে (FIFO) রাখা হয়। একসাথে কয়েকটি ব্লক বেল্টে থাকতে পারে, এবং কোনো ট্র্যাকিং হার্ডওয়্যার কিনতে হয়নি। আগমন সেন্সর ও সারি মিললেই কেবল ব্লক ঠেলে দেওয়া হয়।'],
  'FIFO queue · 32-bit timer · zone handoff': ['FIFO 대기열 · 32비트 타이머 · 구역 인계', 'FIFO সারি · ৩২-বিট টাইমার · জোন হস্তান্তর'],
  'Fixes from the test run': ['시운전에서 고친 문제', 'পরীক্ষামূলক চালনার সংশোধন'],
  'The sensor reading changed while a block was leaving the sensors, so it went to the wrong bin. The fix holds the size result until the block has fully passed. The arrival sensor flickered, so it now has an on-delay filter.': [
    '블록이 센서를 빠져나가는 동안 센서 값이 바뀌어 잘못된 상자로 간 문제가 있었습니다. 블록이 완전히 지나갈 때까지 판정 결과를 유지하도록 고쳤습니다. 도착 센서 신호가 떨려서 온딜레이 필터를 추가했습니다.',
    'ব্লক সেন্সর ছেড়ে যাওয়ার সময় সেন্সরের রিডিং বদলে যেত, ফলে সেটি ভুল বাক্সে যেত। সমাধান হিসেবে ব্লক পুরোপুরি পার না হওয়া পর্যন্ত আকারের ফল ধরে রাখা হয়। আগমন সেন্সর কাঁপছিল, তাই এখন এতে অন-ডিলে ফিল্টার আছে।'],
  'Latch · on-delay filter · edge detection': ['래치 · 온딜레이 필터 · 엣지 검출', 'ল্যাচ · অন-ডিলে ফিল্টার · এজ ডিটেকশন'],
  'Safe stop and restart': ['안전한 정지와 재기동', 'নিরাপদে থামা ও পুনরায় চালু'],
  'A normal stop runs the belt until it is empty. An emergency stop cuts all outputs at once. To restart, the line steps from Reset (clear data, return cylinders) to Safe to Idle, so nothing moves suddenly.': [
    '일반 정지는 벨트가 빌 때까지 운전한 뒤 멈춥니다. 비상정지는 모든 출력을 즉시 차단합니다. 재기동은 리셋(데이터 초기화, 실린더 복귀) → 안전 → 대기 순서로 진행해 갑자기 움직이는 일이 없습니다.',
    'সাধারণ স্টপে বেল্ট খালি না হওয়া পর্যন্ত চলে। জরুরি স্টপ একসাথে সব আউটপুট বন্ধ করে দেয়। পুনরায় চালু করতে লাইনটি রিসেট (ডেটা মোছা, সিলিন্ডার ফেরানো) থেকে সেফ হয়ে আইডলে যায়, তাই হঠাৎ কিছু নড়ে না।'],
  'Drain mode · E-stop · interlocks': ['드레인 모드 · 비상정지 · 인터록', 'ড্রেন মোড · জরুরি স্টপ · ইন্টারলক'],
  'Error system': ['에러 시스템', 'এরর সিস্টেম'],
  'Alarms are bit-mapped by zone and split into guide messages, light alarms (the line waits) and heavy alarms (the line stops). A broken upstream sensor is found from an empty handoff buffer, not from an extra sensor.': [
    '알람은 구역별 비트맵으로 관리하며 가이드 메시지, 경알람(라인 대기), 중알람(라인 정지)으로 나뉩니다. 앞단 센서 고장은 센서를 추가하지 않고, 비어 있는 인계 버퍼로 찾아냅니다.',
    'অ্যালার্মগুলো জোন অনুযায়ী বিট-ম্যাপ করা এবং গাইড বার্তা, হালকা অ্যালার্ম (লাইন অপেক্ষা করে) ও ভারী অ্যালার্মে (লাইন থামে) ভাগ করা। আগের ধাপের নষ্ট সেন্সর বাড়তি সেন্সর দিয়ে নয়, খালি হস্তান্তর বাফার দেখে শনাক্ত হয়।'],
  'Bit-mapped alarms · HMI guidance': ['비트맵 알람 · HMI 안내', 'বিট-ম্যাপড অ্যালার্ম · HMI নির্দেশনা'],
  'Delivered with a wiring and pneumatic circuit diagram, flowchart, parts list, I/O list, error list, parameter list and a user and maintenance manual.': [
    '전기·공압 회로도, 플로차트, 부품표, I/O 목록, 에러 목록, 파라미터 목록, 사용자·유지보수 매뉴얼을 함께 제출했습니다.',
    'ওয়্যারিং ও নিউমেটিক সার্কিট ডায়াগ্রাম, ফ্লোচার্ট, যন্ত্রাংশের তালিকা, I/O তালিকা, এরর তালিকা, প্যারামিটার তালিকা এবং ব্যবহারকারী ও রক্ষণাবেক্ষণ ম্যানুয়ালসহ জমা দেওয়া হয়েছে।'],
  'PLC, HMI, Python and drawings on GitHub ↗': ['GitHub의 PLC · HMI · Python · 도면 ↗', 'GitHub-এ PLC, HMI, Python ও ড্রয়িং ↗'],

  // ---------- elevator ----------
  '6-Floor Elevator with AC Motor and Pneumatics': ['AC 모터와 공압을 활용한 6층 승강기', 'AC মোটর ও নিউমেটিক্সসহ ৬ তলার লিফট'],
  'Sep – Oct 2026': ['2026년 9월 – 10월', 'সেপ্টেম্বর – অক্টোবর ২০২৬'],
  'Result': ['결과', 'ফলাফল'],
  'passed acceptance test': ['검사 합격', 'গ্রহণযোগ্যতা পরীক্ষায় উত্তীর্ণ'],
  'HMI floor buttons: floors 5 and 2 are red because the car will stop there; the other floors are blue. The car is at floor 3, moving up.': [
    'HMI 층 버튼: 승강기가 멈출 5층과 2층은 빨간색, 나머지 층은 파란색입니다. 승강기는 3층에서 올라가는 중입니다.',
    'HMI তলার বোতাম: ৫ ও ২ তলা লাল, কারণ লিফট সেখানে থামবে; বাকি তলাগুলো নীল। লিফটটি ৩ তলায়, উপরে যাচ্ছে।'],
  'stop': ['정지', 'থামবে'],
  "HMI floor buttons: red means the car will stop there, blue means it won't.": [
    'HMI 층 버튼: 빨간색은 승강기가 멈추는 층, 파란색은 멈추지 않는 층입니다.',
    'HMI তলার বোতাম: লাল মানে লিফট সেখানে থামবে, নীল মানে থামবে না।'],
  'A working 6-floor elevator model. An AC motor with a speed controller moves the car, a pneumatic cylinder acts as the door, and a sensor on every floor reads a flag on the car. Each floor has hall call buttons (Up only at floor 1, Down only at floor 6). Inside the car, the floor buttons, the direction arrows and the door open/close buttons are on a touchscreen HMI.': [
    '실제로 동작하는 6층 승강기 모형입니다. 속도 조절기가 달린 AC 모터가 승강기를 움직이고, 공압 실린더가 문 역할을 하며, 각 층의 센서가 승강기의 센서 플래그를 감지합니다. 각 층에는 호출 버튼이 있습니다(1층은 상승만, 6층은 하강만). 승강기 안의 층 버튼, 방향 표시, 문 열림/닫힘 버튼은 터치스크린 HMI에 있습니다.',
    'একটি সচল ৬ তলার লিফট মডেল। স্পিড কন্ট্রোলারসহ একটি AC মোটর লিফট চালায়, একটি নিউমেটিক সিলিন্ডার দরজার কাজ করে, এবং প্রতিটি তলার সেন্সর লিফটের একটি ফ্ল্যাগ পড়ে। প্রতিটি তলায় কল বোতাম আছে (১ তলায় শুধু উপরে, ৬ তলায় শুধু নিচে)। লিফটের ভেতরের তলার বোতাম, দিক নির্দেশক তীর ও দরজা খোলা/বন্ধের বোতাম একটি টাচস্ক্রিন HMI-তে আছে।'],
  'Control sequence': ['제어 순서', 'নিয়ন্ত্রণের ধাপ'],
  'Read calls': ['호출 입력', 'কল পড়া'],
  'Find current floor': ['현재 층 확인', 'বর্তমান তলা নির্ণয়'],
  'Pick target floor': ['목표 층 결정', 'লক্ষ্য তলা বাছাই'],
  'Up or down': ['상승 / 하강 판단', 'উপরে না নিচে'],
  'Run motor': ['모터 운전', 'মোটর চালানো'],
  'Stop, open door': ['정지, 문 열림', 'থামা, দরজা খোলা'],
  'PLC program': ['PLC 프로그램', 'PLC প্রোগ্রাম'],
  'Split into six programs, one per job: switch input, floor sensing, direction, floor request, arrival and motor drive. Sensor states become position values in D00000, and the target goes in D00001. Comparing the two decides whether the car goes up or down. Timers handle the door after the car arrives.': [
    '기능별로 6개 프로그램으로 나눴습니다: 스위치 입력, 층 감지, 방향 판단, 층 입력, 도착, 모터 구동. 센서 상태를 D00000의 위치 값으로 바꾸고, 목표 층은 D00001에 저장합니다. 두 값을 비교해 상승·하강을 결정합니다. 도착 후 문 동작은 타이머로 처리합니다.',
    'প্রতিটি কাজের জন্য একটি করে ছয়টি প্রোগ্রামে ভাগ করা: সুইচ ইনপুট, তলা শনাক্তকরণ, দিক, তলার অনুরোধ, পৌঁছানো ও মোটর চালনা। সেন্সরের অবস্থা D00000-এ অবস্থানের মান হয়, আর লক্ষ্য তলা D00001-এ যায়। দুটির তুলনা করে লিফট উপরে না নিচে যাবে ঠিক হয়। লিফট পৌঁছানোর পর টাইমার দরজা সামলায়।'],
  'XG5000 ladder · counters · timers': ['XG5000 래더 · 카운터 · 타이머', 'XG5000 ল্যাডার · কাউন্টার · টাইমার'],
  'Safe elevator behaviour': ['안전한 승강기 동작', 'নিরাপদ লিফট আচরণ'],
  'The car stops only at floors called in its direction of travel and ignores calls for floors it has already passed. The door stays shut while the car is moving. An emergency stop halts everything, and the car runs again after the stop is released.': [
    '승강기는 진행 방향으로 호출된 층에서만 멈추고, 이미 지나친 층의 호출에는 반응하지 않습니다. 이동 중에는 문이 열리지 않습니다. 비상정지를 누르면 모든 동작이 멈추고, 해제하면 다시 운전합니다.',
    'লিফট শুধু তার চলার দিকে ডাকা তলাগুলোতেই থামে এবং আগেই পার হওয়া তলার কল উপেক্ষা করে। চলার সময় দরজা বন্ধ থাকে। জরুরি স্টপ সব থামিয়ে দেয়, আর স্টপ ছাড়ার পর লিফট আবার চলে।'],
  'Call priority · door interlock · E-stop': ['호출 우선순위 · 문 인터록 · 비상정지', 'কলের অগ্রাধিকার · দরজা ইন্টারলক · জরুরি স্টপ'],
  'HMI and documentation': ['HMI와 문서', 'HMI ও ডকুমেন্টেশন'],
  'The operator screen was built in TOP Design Studio, with a car status view, direction arrows, floor buttons and door controls. The team also wrote a user manual, a control flowchart, a parts list and a test report.': [
    '운영 화면은 TOP Design Studio로 만들었으며 승강기 상태, 방향 표시, 층 버튼, 문 조작 버튼이 있습니다. 팀은 사용자 매뉴얼, 제어 플로차트, 부품표, 시험 성적서도 작성했습니다.',
    'অপারেটর স্ক্রিনটি TOP Design Studio-তে তৈরি, যাতে লিফটের অবস্থা, দিক নির্দেশক তীর, তলার বোতাম ও দরজার নিয়ন্ত্রণ আছে। দলটি একটি ব্যবহারকারী ম্যানুয়াল, নিয়ন্ত্রণ ফ্লোচার্ট, যন্ত্রাংশের তালিকা ও পরীক্ষার প্রতিবেদনও লিখেছে।'],
  'TOP Design Studio · user manual · test report': ['TOP Design Studio · 사용자 매뉴얼 · 시험 성적서', 'TOP Design Studio · ব্যবহারকারী ম্যানুয়াল · পরীক্ষার প্রতিবেদন'],
  'Passed all 9 requirements and 9 of the 10 functional tests.': ['요구사항 9개를 모두 충족하고, 기능 시험 10개 중 9개를 통과했습니다.', '৯টি প্রয়োজনীয়তার সবগুলো এবং ১০টি কার্যকরী পরীক্ষার ৯টিতে উত্তীর্ণ।'],
  "The one marginal result was speed control: the motor speed setting is safe up to level 3 (limit 3.5). From level 4, the car's inertia carries it past the floor, so that range was written into the test report.": [
    '유일하게 조건부였던 항목은 속도 조절입니다. 모터 속도는 3단계까지 안전하고(한계 3.5), 4단계부터는 관성 때문에 층을 지나쳐 멈추므로 이 범위를 시험 성적서에 기록했습니다.',
    'একমাত্র সীমান্তবর্তী ফল ছিল গতি নিয়ন্ত্রণ: মোটরের গতি লেভেল ৩ পর্যন্ত নিরাপদ (সীমা ৩.৫)। লেভেল ৪ থেকে লিফটের জড়তা তাকে তলা পার করে নিয়ে যায়, তাই এই সীমাটি পরীক্ষার প্রতিবেদনে লেখা হয়েছে।'],
  'PLC, HMI and docs on GitHub ↗': ['GitHub의 PLC · HMI · 문서 ↗', 'GitHub-এ PLC, HMI ও ডকুমেন্ট ↗'],
  '3D simulator of the 6-floor elevator': ['6층 승강기 3D 시뮬레이터', '৬ তলার লিফটের 3D সিমুলেটর'],
  'Load the 3D elevator simulator': ['3D 승강기 시뮬레이터 불러오기', '3D লিফট সিমুলেটর লোড করুন'],
  "Built from the elevator's STEP assembly. Press hall buttons or the car's HMI floor buttons (also clickable in 3D) and watch the car serve calls in travel order. Try speed setting 4 to see the overshoot found in test 04, block the doorway, or hit the E-stop.": [
    '승강기의 STEP 어셈블리로 만들었습니다. 층 호출 버튼이나 승강기 HMI의 층 버튼(3D에서도 클릭 가능)을 누르면 승강기가 진행 순서대로 호출을 처리합니다. 속도를 4로 올려 시험 04에서 발견한 정지 위치 초과를 확인하거나, 문 앞을 막거나, 비상정지를 눌러 보세요.',
    'লিফটের STEP অ্যাসেম্বলি থেকে তৈরি। তলার কল বোতাম বা লিফটের HMI-এর তলার বোতাম চাপুন (3D-তেও ক্লিক করা যায়) এবং দেখুন লিফট চলার ক্রম অনুযায়ী কলগুলো সামলায়। পরীক্ষা ০৪-এ পাওয়া ওভারশুট দেখতে গতি ৪ দিন, দরজার পথ আটকান, অথবা জরুরি স্টপ চাপুন।'],

  // ---------- background (from CV) ----------
  'Education & experience ↓': ['학력 및 경력 ↓', 'শিক্ষা ও অভিজ্ঞতা ↓'],
  'Background': ['배경', 'পটভূমি'],
  'Education and experience': ['학력 및 경력', 'শিক্ষা ও অভিজ্ঞতা'],
  "I come to automation from physics and chip design. My master's research was on neuromorphic circuits, followed by two years as a design engineer for engine turbochargers. I am now training full time in PLC, HMI, SCADA, motion control and machine vision, and I am looking for a role as a maintenance or automation engineer.":
    ['물리학과 반도체 칩 설계를 거쳐 자동화 분야로 왔습니다. 석사 과정에서 뉴로모픽 회로를 연구했고, 이후 2년간 엔진 터보차저 설계 엔지니어로 일했습니다. 현재 PLC, HMI, SCADA, 모션 제어, 머신 비전을 전일제로 교육받고 있으며, 설비 보전 엔지니어 또는 자동화 엔지니어 직무를 찾고 있습니다.',
     'আমি পদার্থবিজ্ঞান ও চিপ ডিজাইন থেকে অটোমেশনে এসেছি। মাস্টার্সে আমার গবেষণা ছিল নিউরোমরফিক সার্কিট নিয়ে, এরপর দুই বছর ইঞ্জিন টার্বোচার্জারের ডিজাইন ইঞ্জিনিয়ার হিসেবে কাজ করেছি। এখন আমি PLC, HMI, SCADA, মোশন কন্ট্রোল ও মেশিন ভিশনে পূর্ণকালীন প্রশিক্ষণ নিচ্ছি এবং মেইনটেন্যান্স বা অটোমেশন ইঞ্জিনিয়ার পদে কাজ খুঁজছি।'],
  'Work experience': ['경력', 'কাজের অভিজ্ঞতা'],
  'Engine Turbocharger Design Engineer': ['엔진 터보차저 설계 엔지니어', 'ইঞ্জিন টার্বোচার্জার ডিজাইন ইঞ্জিনিয়ার'],
  'Professional training': ['전문 교육', 'পেশাগত প্রশিক্ষণ'],
  'Industrial automation and robotics': ['산업 자동화 및 로보틱스', 'শিল্প অটোমেশন ও রোবোটিক্স'],
  'PLC and HMI programming, SCADA, motion and servo control, sensors, machine vision and Python. The four projects on this page were built during this course.':
    ['PLC·HMI 프로그래밍, SCADA, 모션 및 서보 제어, 센서, 머신 비전, Python. 이 페이지의 네 가지 프로젝트는 이 과정에서 만들었습니다.',
     'PLC ও HMI প্রোগ্রামিং, SCADA, মোশন ও সার্ভো কন্ট্রোল, সেন্সর, মেশিন ভিশন ও Python। এই পাতার চারটি প্রকল্প এই কোর্সেই তৈরি।'],
  'Research': ['연구', 'গবেষণা'],
  'Neuromorphic circuits': ['뉴로모픽 회로', 'নিউরোমরফিক সার্কিট'],
  '· Nano Circuit Design Lab, Inje University ·': ['· 인제대학교 나노회로설계(NCDL) 연구실 ·', '· ন্যানো সার্কিট ডিজাইন ল্যাব, ইনজে বিশ্ববিদ্যালয় ·'],
  'Designed and built artificial neuron, synapse and TIA circuits in 65 nm CMOS, then measured and characterised the chips and analysed the test data.':
    ['65 nm CMOS 기반 인공 뉴런·시냅스·TIA 회로를 설계·구현하고, 칩 측정 및 특성 분석, 실험 데이터 분석과 성능 검증을 수행했습니다.',
     '65 nm CMOS-এ কৃত্রিম নিউরন, সিন্যাপ্স ও TIA সার্কিট ডিজাইন ও তৈরি করেছি, তারপর চিপ পরিমাপ ও বৈশিষ্ট্য নির্ণয় করে পরীক্ষার ডেটা বিশ্লেষণ করেছি।'],
  'Publication': ['논문', 'প্রকাশনা'],
  'All my publications on Google Scholar ↗': ['Google Scholar에서 전체 논문 보기 ↗', 'Google Scholar-এ আমার সব প্রকাশনা ↗'],
  'Period': ['기간', 'সময়কাল'],
  'School': ['학교', 'প্রতিষ্ঠান'],
  'Degree': ['학위', 'ডিগ্রি'],
  'Inje University, Korea': ['인제대학교 (한국)', 'ইনজে বিশ্ববিদ্যালয়, কোরিয়া'],
  'Khulna University, Bangladesh': ['쿨나대학교 (방글라데시)', 'খুলনা বিশ্ববিদ্যালয়, বাংলাদেশ'],
  'M.Sc., Nano-science & Engineering': ['나노과학공학 석사', 'এম.এসসি., ন্যানো-বিজ্ঞান ও প্রকৌশল'],
  'B.Sc., Physics': ['물리학 학사', 'বি.এসসি., পদার্থবিজ্ঞান'],
  'Electronics': ['전자', 'ইলেকট্রনিক্স'],
  'Circuit design': ['회로 설계', 'সার্কিট ডিজাইন'],
  'PCB design': ['PCB 설계', 'PCB ডিজাইন'],
  'Measurement and testing': ['측정 및 시험', 'পরিমাপ ও পরীক্ষা'],
  'Programming and CAD': ['프로그래밍 및 CAD', 'প্রোগ্রামিং ও CAD'],
  'Languages': ['언어 능력', 'ভাষা দক্ষতা'],
  'Bengali · native': ['벵골어 · 모국어', 'বাংলা · মাতৃভাষা'],
  'English · TOEIC 750, IELTS 6.0': ['영어 · TOEIC 750, IELTS 6.0', 'ইংরেজি · TOEIC 750, IELTS 6.0'],
  'Korean · KIIP level 4': ['한국어 · 사회통합프로그램(KIIP) 4단계', 'কোরিয়ান · KIIP লেভেল ৪'],

  // ---------- footer ----------
  'Md Nazmul Haque · 2026': ['Md Nazmul Haque · 2026', 'মোঃ নাজমুল হক · ২০২৬'],
};
