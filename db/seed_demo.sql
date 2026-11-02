-- =====================================================================
-- Gravity Fitness Club - DEMO data (30 members), dates relative to today
--
-- Run (from project root), with YOUR OWN WhatsApp number for every member,
-- so a WhatsApp test never messages a stranger:
--   psql -d gym_admin -v demo_mobile=9XXXXXXXXX -f db/seed_demo.sql
--   (add -U <user> if your PostgreSQL login is not your OS user)
--
-- Only runs when the members table is empty. Remove the demo before go-live:
--   see "CLEAR ALL MEMBER DATA" in db/common_queries.sql
-- =====================================================================

\set ON_ERROR_STOP on

\if :{?demo_mobile}
\else
  \echo 'Missing mobile. Usage: psql -d gym_admin -v demo_mobile=9XXXXXXXXX -f db/seed_demo.sql'
  \quit
\endif

SET timezone = 'Asia/Kolkata';
-- psql variables do not work inside $$ ... $$, so pass the number through a setting
SELECT set_config('demo.mobile', :'demo_mobile', false) AS demo_mobile;

DO $$
DECLARE
    mobile text := current_setting('demo.mobile');
    -- first, last, guardian, sex, age, end (days from today), package, objective, food,
    -- address, weight, height, sugar, bp, mode, older renewals, reminder sent (hours ago, '' = never)
    demo text[] := ARRAY[
        -- 4 due soon: today, tomorrow, tomorrow, day after
        ['Vishal','Ojha','Ramesh Ojha','M','24','0','1 Month','Fat loss','Non-veg','Ward 7, Kasia','86','5.10','No','No','UPI','2','3'],
        ['Priya','Singh','Rakesh Singh','F','22','1','1 Month','General fitness','Veg','Civil Lines, Padrauna','58','5.3','No','No','Cash','0',''],
        ['Rohit','Gupta','Suresh Gupta','M','29','1','3 Months','Muscle gain','Eggetarian','Station Road, Kasia','72','5.9','No','No','Cash','1','26'],
        ['Aman','Yadav','Shivnath Yadav','M','31','2','1 Month','Weight gain','Veg','Hata Bazaar, Hata','61','5.8','No','Low','UPI','0',''],
        -- 4 expired: 1, 5, 12 and 45 days ago
        ['Neha','Pandey','Arvind Pandey','F','27','-1','1 Month','Fat loss','Veg','Buddha Marg, Kushinagar','68','5.4','No','No','Cash','0','50'],
        ['Deepak','Maurya','Ramlal Maurya','M','35','-5','3 Months','General fitness','Non-veg','Tamkuhi Road, Kasia','79','5.7','Yes','High','Card','0','150'],
        ['Sanjay','Kushwaha','Bhola Kushwaha','M','40','-12','1 Month','Fat loss','Veg','Sewarhi, Kushinagar','92','5.6','Yes','No','Cash','0',''],
        ['Pooja','Mishra','Vinod Mishra','F','30','-45','1 Month','General fitness','Veg','Kaptanganj, Kushinagar','63','5.2','No','No','UPI','0',''],
        -- 22 active
        ['Ankit','Mishra','Dinesh Mishra','M','23','18','1 Month','Muscle gain','Non-veg','Ward 3, Kasia','66','5.11','No','No','UPI','0',''],
        ['Ritu','Chauhan','Mahesh Chauhan','F','26','160','6 Months','Fat loss','Veg','Fazilnagar, Kushinagar','71','5.4','No','No','Card','0',''],
        ['Sonu','Kushwaha','Lalji Kushwaha','M','21','75','3 Months','Muscle gain','Eggetarian','Ramkola, Kushinagar','64','5.8','No','No','Cash','1',''],
        ['Rahul','Tiwari','Prem Tiwari','M','28','340','1 Year','Muscle gain','Non-veg','Gandhi Nagar, Kasia','77','6','No','No','UPI','0',''],
        ['Anjali','Verma','Sunil Verma','F','24','12','1 Month','Fat loss','Veg','Kasia Bazaar, Kasia','62','5.3','No','No','UPI','0',''],
        ['Manoj','Prajapati','Hiralal Prajapati','M','38','70','3 Months','General fitness','Veg','Khadda, Kushinagar','82','5.7','Yes','No','Cash','0',''],
        ['Sunita','Devi','Ramesh Prasad','F','42','22','1 Month','Fat loss','Veg','Ward 12, Kasia','74','5.1','Yes','High','Cash','0',''],
        ['Abhishek','Shukla','Ajay Shukla','M','25','165','6 Months','Muscle gain','Non-veg','Padrauna Road, Kasia','70','5.10','No','No','Card','0',''],
        ['Kajal','Gupta','Rajendra Gupta','F','20','9','1 Month','General fitness','Veg','Dudhi, Kushinagar','52','5.2','No','No','UPI','0',''],
        ['Vikas','Patel','Ramdhani Patel','M','33','80','3 Months','Weight gain','Eggetarian','Hata, Kushinagar','59','5.9','No','No','UPI','0',''],
        ['Shivam','Rai','Umesh Rai','M','22','26','1 Month','Muscle gain','Non-veg','Station Road, Kasia','68','5.8','No','No','Cash','0',''],
        ['Nisha','Yadav','Ramnaresh Yadav','F','29','350','1 Year','Fat loss','Veg','Turkpatti, Kushinagar','66','5.5','No','Low','Card','0',''],
        ['Arjun','Singh','Brijesh Singh','M','27','15','1 Month','Muscle gain','Non-veg','Buddha Marg, Kushinagar','75','6.1','No','No','UPI','1',''],
        ['Rekha','Sharma','Om Prakash Sharma','F','45','65','3 Months','General fitness','Veg','Civil Lines, Padrauna','70','5.2','Yes','High','Cash','0',''],
        ['Mohit','Jaiswal','Santosh Jaiswal','M','19','20','1 Month','Weight gain','Veg','Ward 9, Kasia','55','5.7','No','No','UPI','0',''],
        ['Pradeep','Nishad','Ramu Nishad','M','36','155','6 Months','Fat loss','Non-veg','Kasia Road, Kushinagar','84','5.6','No','No','Cash','0',''],
        ['Saloni','Srivastava','Alok Srivastava','F','23','7','1 Month','General fitness','Eggetarian','Ram Nagar, Kasia','57','5.4','No','No','UPI','0',''],
        ['Rajesh','Kumar','Shyam Lal','M','41','85','3 Months','Fat loss','Veg','Tamkuhi Raj, Kushinagar','88','5.8','Yes','No','Cash','0',''],
        ['Gaurav','Pandey','Kamlesh Pandey','M','26','24','1 Month','Muscle gain','Non-veg','Kushinagar Road, Kasia','73','5.11','No','No','UPI','0',''],
        ['Komal','Maurya','Jagdish Maurya','F','21','172','6 Months','Fat loss','Veg','Sewarhi, Kushinagar','69','5.3','No','No','Card','0',''],
        ['Sachin','Yadav','Rampal Yadav','M','30','11','1 Month','General fitness','Non-veg','Ward 2, Kasia','80','5.9','No','No','UPI','0',''],
        ['Divya','Tripathi','Anand Tripathi','F','28','335','1 Year','General fitness','Veg','Kaptanganj, Kushinagar','60','5.5','No','No','Card','0','']
    ];
    r text[];
    pkg record;
    n int := 0;
    m_id int;
    end_d date;
    start_d date;
    first_start date;
    prev_start date;
    prev_end date;
    paid date;
BEGIN
    IF mobile !~ '^[0-9]{10}$' THEN
        RAISE EXCEPTION 'demo_mobile must be exactly 10 digits, got "%"', mobile;
    END IF;
    IF EXISTS (SELECT 1 FROM members) THEN
        RAISE NOTICE 'members table is not empty - demo seed skipped, nothing changed.';
        RETURN;
    END IF;

    FOREACH r SLICE 1 IN ARRAY demo LOOP
        n := n + 1;
        SELECT * INTO pkg FROM packages WHERE name = r[7];
        end_d := CURRENT_DATE + r[6]::int;
        start_d := ((end_d + 1) - make_interval(months => pkg.months))::date;

        -- older periods (renewals) go back in time from the current one
        first_start := start_d;
        prev_end := start_d - 1;
        FOR i IN 1 .. r[16]::int LOOP
            prev_start := ((prev_end + 1) - make_interval(months => pkg.months))::date;
            first_start := prev_start;
            prev_end := prev_start - 1;
        END LOOP;

        INSERT INTO members (first_name, last_name, guardian_name, sex, age, mobile, address,
                             weight_kg, height, food_type, objective, sugar, blood_pressure, disease,
                             package_id, start_date, end_date, fee, last_reminder_at, created_at)
        VALUES (r[1], r[2], r[3], r[4], r[5]::int, mobile, r[10], r[11]::numeric, r[12], r[9], r[8],
                r[13] = 'Yes', r[14], CASE WHEN r[13] = 'Yes' THEN 'Sugar - on medicine' END,
                pkg.id, start_d, end_d, pkg.price,
                CASE WHEN r[17] <> '' THEN now() - make_interval(hours => r[17]::int) END,
                first_start + time '10:30')
        RETURNING id INTO m_id;

        -- older payments
        prev_end := start_d - 1;
        FOR i IN 1 .. r[16]::int LOOP
            prev_start := ((prev_end + 1) - make_interval(months => pkg.months))::date;
            INSERT INTO payments (member_id, package_id, amount, mode, period_start, period_end, paid_on, created_at)
            VALUES (m_id, pkg.id, pkg.price, r[15], prev_start, prev_end, prev_start, prev_start + time '10:30');
            prev_end := prev_start - 1;
        END LOOP;

        -- current payment: normally on the start date; every 4th member paid late (today)
        -- so "Collected this month" always has a real number, even on the 1st
        paid := LEAST(start_d, CURRENT_DATE);
        IF n % 4 = 0 AND start_d < date_trunc('month', CURRENT_DATE) AND r[6]::int >= 0 THEN
            paid := CURRENT_DATE;
        END IF;
        INSERT INTO payments (member_id, package_id, amount, mode, period_start, period_end, paid_on, created_at)
        VALUES (m_id, pkg.id, pkg.price, r[15], start_d, end_d, paid, paid + time '11:00');
    END LOOP;

    RAISE NOTICE 'Demo data added: % members, all with mobile %', n, mobile;
END $$;

SELECT
    COUNT(*) FILTER (WHERE end_date >  CURRENT_DATE + 2)                       AS active,
    COUNT(*) FILTER (WHERE end_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 2) AS due_soon,
    COUNT(*) FILTER (WHERE end_date <  CURRENT_DATE)                           AS expired,
    COUNT(*)                                                                   AS total
FROM members;
