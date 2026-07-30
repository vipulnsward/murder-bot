--
-- PostgreSQL database dump
--

\restrict p3WPumxrZkb4G0C9hoXiIGfCJleX9DtxxNEvdKWrAq7bFOhuZ4vBWexkylEpdWo

-- Dumped from database version 16.14 (Postgres.app)
-- Dumped by pg_dump version 16.14 (Postgres.app)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: app_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_users (
    id integer NOT NULL,
    email text NOT NULL,
    pw_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: app_users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.app_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: app_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.app_users_id_seq OWNED BY public.app_users.id;


--
-- Name: battle_buffs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_buffs (
    id integer NOT NULL,
    report_id integer,
    side text,
    troop_type text,
    kind text,
    attack_pct integer,
    defense_pct integer,
    hp_pct integer
);


--
-- Name: battle_buffs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.battle_buffs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: battle_buffs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.battle_buffs_id_seq OWNED BY public.battle_buffs.id;


--
-- Name: battle_participants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_participants (
    id integer NOT NULL,
    report_id integer,
    side text,
    role text,
    alliance text,
    name text,
    power text,
    primary_general text,
    primary_level integer,
    primary_kills text,
    assistant_general text,
    assistant_level integer,
    assistant_kills text
);


--
-- Name: battle_participants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.battle_participants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: battle_participants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.battle_participants_id_seq OWNED BY public.battle_participants.id;


--
-- Name: battle_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_reports (
    id integer NOT NULL,
    source text,
    kind text,
    outcome text,
    def_alliance text,
    def_name text,
    def_x integer,
    def_y integer,
    def_power text,
    def_lost_power text,
    att_alliance text,
    att_name text,
    att_x integer,
    att_y integer,
    att_power text,
    att_lost_power text,
    def_total bigint,
    def_survived bigint,
    def_wounded bigint,
    def_killed bigint,
    def_captured bigint,
    def_traps bigint,
    att_total bigint,
    att_survived bigint,
    att_wounded bigint,
    att_killed bigint,
    att_captured bigint,
    att_traps bigint,
    ts timestamp with time zone DEFAULT now()
);


--
-- Name: battle_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.battle_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: battle_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.battle_reports_id_seq OWNED BY public.battle_reports.id;


--
-- Name: battle_troop_losses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_troop_losses (
    id integer NOT NULL,
    report_id integer,
    participant text,
    troop_type text,
    tier integer,
    survived bigint,
    killing bigint,
    killed bigint,
    wounded bigint,
    deserter bigint,
    soul bigint
);


--
-- Name: battle_troop_losses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.battle_troop_losses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: battle_troop_losses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.battle_troop_losses_id_seq OWNED BY public.battle_troop_losses.id;


--
-- Name: combat_generals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.combat_generals (
    id integer NOT NULL,
    troop_type text,
    role text,
    name text,
    atk_mult numeric,
    def_mult numeric,
    hp_mult numeric,
    march_mult numeric,
    rally_mult numeric,
    lead_base numeric,
    lead_inc numeric,
    atk_base numeric,
    atk_inc numeric,
    def_base numeric,
    def_inc numeric,
    pol_base numeric
);


--
-- Name: enemies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enemies (
    name text NOT NULL,
    alliance text NOT NULL,
    battles integer DEFAULT 0,
    my_wins integer DEFAULT 0,
    my_losses integer DEFAULT 0,
    max_troops bigint,
    coords text,
    buffs jsonb,
    generals jsonb,
    threat text,
    last_seen timestamp without time zone
);


--
-- Name: evony_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evony_accounts (
    id integer NOT NULL,
    user_id integer,
    label text,
    enc_username text NOT NULL,
    enc_password text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: evony_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.evony_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: evony_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.evony_accounts_id_seq OWNED BY public.evony_accounts.id;


--
-- Name: generals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.generals (
    id integer NOT NULL,
    name text,
    gen_type text,
    level integer,
    stars integer,
    role text,
    owned boolean DEFAULT true,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: generals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.generals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: generals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.generals_id_seq OWNED BY public.combat_generals.id;


--
-- Name: generals_id_seq1; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.generals_id_seq1
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: generals_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.generals_id_seq1 OWNED BY public.generals.id;


--
-- Name: integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.integrations (
    id integer NOT NULL,
    user_id integer,
    kind text NOT NULL,
    enc_value text NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: integrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.integrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: integrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.integrations_id_seq OWNED BY public.integrations.id;


--
-- Name: knowledge; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge (
    source text NOT NULL,
    source_id text NOT NULL,
    title text,
    url text,
    topic text,
    author text,
    text text,
    n_chars integer,
    ingested_at timestamp without time zone DEFAULT now()
);


--
-- Name: preset_troops; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preset_troops (
    id integer NOT NULL,
    preset_id integer,
    name text,
    tier integer,
    count bigint
);


--
-- Name: preset_troops_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.preset_troops_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: preset_troops_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.preset_troops_id_seq OWNED BY public.preset_troops.id;


--
-- Name: presets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.presets (
    id integer NOT NULL,
    troop_type text,
    main_general text,
    assistant_general text,
    skill text,
    march bigint,
    march_max bigint,
    attack bigint,
    load bigint
);


--
-- Name: presets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.presets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: presets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.presets_id_seq OWNED BY public.presets.id;


--
-- Name: report_extracts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_extracts (
    rid text NOT NULL,
    title text,
    outcome text,
    ts text,
    coords text,
    defender text,
    attacker text,
    killed bigint,
    wounded bigint,
    lost_power bigint,
    destroyed_traps bigint,
    deserter bigint,
    holy_palace bigint,
    subcity_kills bigint,
    participants jsonb,
    stats jsonb,
    buffs jsonb,
    raw_text text,
    updated_at timestamp with time zone DEFAULT now(),
    reinforcements jsonb,
    subordinate_city jsonb,
    main_general jsonb,
    assistant_general jsonb,
    battle_details jsonb
);


--
-- Name: subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subscriptions (
    id integer NOT NULL,
    user_id integer,
    plan text DEFAULT 'free'::text NOT NULL,
    status text DEFAULT 'inactive'::text NOT NULL,
    provider text DEFAULT 'razorpay'::text,
    provider_id text,
    current_period_end timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.subscriptions_id_seq OWNED BY public.subscriptions.id;


--
-- Name: troops; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.troops (
    id integer NOT NULL,
    building text,
    tier integer,
    name text,
    own bigint,
    cost_food bigint,
    cost_wood bigint,
    cost_stone bigint,
    cost_ore bigint,
    cost_gold bigint,
    train_seconds bigint,
    instant_gems bigint,
    locked boolean
);


--
-- Name: troops_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.troops_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: troops_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.troops_id_seq OWNED BY public.troops.id;


--
-- Name: app_users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users ALTER COLUMN id SET DEFAULT nextval('public.app_users_id_seq'::regclass);


--
-- Name: battle_buffs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_buffs ALTER COLUMN id SET DEFAULT nextval('public.battle_buffs_id_seq'::regclass);


--
-- Name: battle_participants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_participants ALTER COLUMN id SET DEFAULT nextval('public.battle_participants_id_seq'::regclass);


--
-- Name: battle_reports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_reports ALTER COLUMN id SET DEFAULT nextval('public.battle_reports_id_seq'::regclass);


--
-- Name: battle_troop_losses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_troop_losses ALTER COLUMN id SET DEFAULT nextval('public.battle_troop_losses_id_seq'::regclass);


--
-- Name: combat_generals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.combat_generals ALTER COLUMN id SET DEFAULT nextval('public.generals_id_seq'::regclass);


--
-- Name: evony_accounts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evony_accounts ALTER COLUMN id SET DEFAULT nextval('public.evony_accounts_id_seq'::regclass);


--
-- Name: generals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generals ALTER COLUMN id SET DEFAULT nextval('public.generals_id_seq1'::regclass);


--
-- Name: integrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations ALTER COLUMN id SET DEFAULT nextval('public.integrations_id_seq'::regclass);


--
-- Name: preset_troops id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preset_troops ALTER COLUMN id SET DEFAULT nextval('public.preset_troops_id_seq'::regclass);


--
-- Name: presets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presets ALTER COLUMN id SET DEFAULT nextval('public.presets_id_seq'::regclass);


--
-- Name: subscriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions ALTER COLUMN id SET DEFAULT nextval('public.subscriptions_id_seq'::regclass);


--
-- Name: troops id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.troops ALTER COLUMN id SET DEFAULT nextval('public.troops_id_seq'::regclass);


--
-- Name: app_users app_users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_email_key UNIQUE (email);


--
-- Name: app_users app_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_pkey PRIMARY KEY (id);


--
-- Name: battle_buffs battle_buffs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_buffs
    ADD CONSTRAINT battle_buffs_pkey PRIMARY KEY (id);


--
-- Name: battle_participants battle_participants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_participants
    ADD CONSTRAINT battle_participants_pkey PRIMARY KEY (id);


--
-- Name: battle_reports battle_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_reports
    ADD CONSTRAINT battle_reports_pkey PRIMARY KEY (id);


--
-- Name: battle_troop_losses battle_troop_losses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_troop_losses
    ADD CONSTRAINT battle_troop_losses_pkey PRIMARY KEY (id);


--
-- Name: enemies enemies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enemies
    ADD CONSTRAINT enemies_pkey PRIMARY KEY (alliance, name);


--
-- Name: evony_accounts evony_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evony_accounts
    ADD CONSTRAINT evony_accounts_pkey PRIMARY KEY (id);


--
-- Name: generals generals_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generals
    ADD CONSTRAINT generals_name_key UNIQUE (name);


--
-- Name: combat_generals generals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.combat_generals
    ADD CONSTRAINT generals_pkey PRIMARY KEY (id);


--
-- Name: generals generals_pkey1; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generals
    ADD CONSTRAINT generals_pkey1 PRIMARY KEY (id);


--
-- Name: combat_generals generals_troop_type_role_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.combat_generals
    ADD CONSTRAINT generals_troop_type_role_name_key UNIQUE (troop_type, role, name);


--
-- Name: integrations integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_pkey PRIMARY KEY (id);


--
-- Name: integrations integrations_user_id_kind_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_user_id_kind_key UNIQUE (user_id, kind);


--
-- Name: knowledge knowledge_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge
    ADD CONSTRAINT knowledge_pkey PRIMARY KEY (source, source_id);


--
-- Name: preset_troops preset_troops_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preset_troops
    ADD CONSTRAINT preset_troops_pkey PRIMARY KEY (id);


--
-- Name: presets presets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presets
    ADD CONSTRAINT presets_pkey PRIMARY KEY (id);


--
-- Name: report_extracts report_extracts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_extracts
    ADD CONSTRAINT report_extracts_pkey PRIMARY KEY (rid);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- Name: subscriptions subscriptions_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_user_id_key UNIQUE (user_id);


--
-- Name: troops troops_building_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.troops
    ADD CONSTRAINT troops_building_name_key UNIQUE (building, name);


--
-- Name: troops troops_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.troops
    ADD CONSTRAINT troops_pkey PRIMARY KEY (id);


--
-- Name: generals_name_lower_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX generals_name_lower_idx ON public.generals USING btree (lower(name));


--
-- Name: knowledge_discord_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX knowledge_discord_ts ON public.knowledge USING btree (source, ingested_at DESC);


--
-- Name: battle_buffs battle_buffs_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_buffs
    ADD CONSTRAINT battle_buffs_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.battle_reports(id) ON DELETE CASCADE;


--
-- Name: battle_participants battle_participants_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_participants
    ADD CONSTRAINT battle_participants_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.battle_reports(id) ON DELETE CASCADE;


--
-- Name: battle_troop_losses battle_troop_losses_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_troop_losses
    ADD CONSTRAINT battle_troop_losses_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.battle_reports(id) ON DELETE CASCADE;


--
-- Name: evony_accounts evony_accounts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evony_accounts
    ADD CONSTRAINT evony_accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.app_users(id) ON DELETE CASCADE;


--
-- Name: integrations integrations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.app_users(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.app_users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict p3WPumxrZkb4G0C9hoXiIGfCJleX9DtxxNEvdKWrAq7bFOhuZ4vBWexkylEpdWo

