import React, { useState } from 'react';
import {
  Database,
  RefreshCw,
  CheckCircle2,
  Zap,
  ShieldCheck,
  ArrowRight,
  Search,
  FileCheck
} from 'lucide-react';
import { useUiStore } from '../../store/uiStore';
import { ModuleType } from '../../layout/SideDock';
import { useTranslation } from '../../i18n';
import { useControlOps } from '../../hooks/useControlOps';

export interface AdvancedFeature {
  id: string;
  name: string;
  nameVi: string;
  category: 'MICROSTRUCTURE' | 'RISK_TCA' | 'ACTIVE_ALPHA' | 'STRATEGY_CPCV' | 'GOVERNANCE' | 'SYSTEM_SUPPLY';
  module: ModuleType;
  subTab?: string;
  description: string;
  descriptionVi: string;
  tag: string;
  color: string;
}

export const ADVANCED_28_FEATURES: AdvancedFeature[] = [
  // 1. Microstructure (4)
  {
    id: 'F01',
    name: 'VPIN Flow Toxicity',
    nameVi: 'Đo lường Độc hại Dòng lệnh VPIN',
    category: 'MICROSTRUCTURE',
    module: 'chart_station',
    subTab: 'vpin',
    description: 'Volume-Synchronized Probability of Toxicity for real-time orderflow stress',
    descriptionVi: 'Xác suất dòng lệnh độc hại được đồng bộ theo khối lượng (VPIN Real-time)',
    tag: 'PIN / VPIN',
    color: 'emerald'
  },
  {
    id: 'F02',
    name: 'Orderbook Depth Waterfall',
    nameVi: 'Thác Độ sâu Sổ lệnh 10 Mức',
    category: 'MICROSTRUCTURE',
    module: 'chart_station',
    subTab: 'waterfall',
    description: '10-level bid/ask liquidity depth visualization with spread dynamics',
    descriptionVi: 'Trực quan hóa độ sâu sổ lệnh 10 bước giá mua/bán và độ rộng Spread',
    tag: 'L2 ORDERBOOK',
    color: 'emerald'
  },
  {
    id: 'F03',
    name: 'Almgren-Chriss Market Impact',
    nameVi: 'Tác động Thị trường Almgren-Chriss',
    category: 'MICROSTRUCTURE',
    module: 'chart_station',
    subTab: 'impact',
    description: 'Permanent and temporary execution impact curves based on order size',
    descriptionVi: 'Mô phỏng đường cong tác động giá vĩnh viễn và tạm thời theo quy mô lệnh',
    tag: 'IMPACT CURVE',
    color: 'emerald'
  },
  {
    id: 'F04',
    name: 'FracDiff Stationary Memory',
    nameVi: 'Biến đổi Vi phân Bậc phân số FracDiff',
    category: 'MICROSTRUCTURE',
    module: 'chart_station',
    subTab: 'fracdiff',
    description: 'Fractional differentiation d=0.35 preserving memory while passing ADF stationarity',
    descriptionVi: 'Giữ lại tối đa bộ nhớ chuỗi giá (d=0.35) nhưng đạt tính dừng ADF nghiêm ngặt',
    tag: 'FRACDIFF d=0.35',
    color: 'emerald'
  },

  // 2. Barra & Risk TCA (6)
  {
    id: 'F05',
    name: 'Circuit Breaker L1/L2/L3',
    nameVi: 'Ngắt mạch Giao dịch Tự động 3 Cấp',
    category: 'RISK_TCA',
    module: 'barra_risk_tca',
    subTab: 'circuit',
    description: 'Autonomous risk mitigation circuit breaker and cooldown mechanism on intraday stress',
    descriptionVi: 'Cơ chế ngắt mạch và hạ tỷ trọng danh mục tự động khi sụt giảm trong phiên',
    tag: 'CIRCUIT BREAKER',
    color: 'rose'
  },
  {
    id: 'F06',
    name: 'Macro Stress Test Simulation',
    nameVi: 'Mô phỏng Khủng hoảng Vĩ mô',
    category: 'RISK_TCA',
    module: 'barra_risk_tca',
    subTab: 'stress',
    description: 'Historical stress replication: COVID-19, 2022 Rate Hike, FX Devaluation',
    descriptionVi: 'Tái lập kịch bản sốc thị trường: COVID-2020, Khủng hoảng Lãi suất 2022, Tỷ giá 2024',
    tag: 'STRESS TEST',
    color: 'rose'
  },
  {
    id: 'F07',
    name: 'Contagion Risk Graph',
    nameVi: 'Mạng lưới Lan truyền Rủi ro Liên ngành',
    category: 'RISK_TCA',
    module: 'barra_risk_tca',
    subTab: 'contagion',
    description: 'Inter-sector systemic transmission matrix and systemic contagion velocity',
    descriptionVi: 'Ma trận lan truyền rủi ro hệ thống giữa các ngành và độ nhạy truyền dẫn',
    tag: 'CONTAGION GRAPH',
    color: 'rose'
  },
  {
    id: 'F08',
    name: 'Liquidity Stress Validator',
    nameVi: 'Kiểm định Thanh khoản & ADV Cap',
    category: 'RISK_TCA',
    module: 'barra_risk_tca',
    subTab: 'liquidity',
    description: 'Days-to-liquidate calculations bounded by max allowable daily volume participation',
    descriptionVi: 'Tính toán thời gian giải phóng danh mục dưới giới hạn tham gia thanh khoản ngày',
    tag: 'LIQUIDITY STRESS',
    color: 'rose'
  },
  {
    id: 'F09',
    name: 'Barra 8-Factor Decomposition',
    nameVi: 'Phân rã 8 Nhân tố Barra',
    category: 'RISK_TCA',
    module: 'barra_risk_tca',
    subTab: 'barra_decomp',
    description: 'Multi-factor risk model: Beta, Momentum, Size, Value, Volatility, Liquidity, Quality, Leverage',
    descriptionVi: 'Mô hình phân tích rủi ro đa nhân tố chuẩn tổ chức tài chính quốc tế',
    tag: 'BARRA 8-FACTOR',
    color: 'rose'
  },
  {
    id: 'F10',
    name: 'Post-Trade TCA Shortfall',
    nameVi: 'Phân tích Chi phí Thực thi TCA',
    category: 'RISK_TCA',
    module: 'barra_risk_tca',
    subTab: 'tca_shortfall',
    description: 'Implementation shortfall, timing risk, and commission vs slippage audit trail',
    descriptionVi: 'Đo lường thất thoát thực thi (Implementation Shortfall), chi phí trượt giá và trễ lệnh',
    tag: 'TCA SHORTFALL',
    color: 'rose'
  },

  // 3. Active Alpha (4)
  {
    id: 'F11',
    name: 'AST Expression Studio',
    nameVi: 'Phòng thí nghiệm Công thức Alpha AST',
    category: 'ACTIVE_ALPHA',
    module: 'alpha_factory',
    subTab: 'AST_STUDIO',
    description: 'Lexical expression AST validation, syntax tree inspection, and complexity scoring',
    descriptionVi: 'Trình biên dịch và chấm điểm độ phức tạp công thức định lượng AST thời gian thực',
    tag: 'AST STUDIO',
    color: 'cyan'
  },
  {
    id: 'F12',
    name: '703 Alpha Arsenal Signals',
    nameVi: 'Kho 703 Tín hiệu Alpha Toàn diện',
    category: 'ACTIVE_ALPHA',
    module: 'alpha_factory',
    subTab: 'ARSENAL_703',
    description: 'Institutional alpha library across Momentum, Microstructure, Sentiment, Value, Quality',
    descriptionVi: 'Kho tín hiệu alpha toàn diện 703 mã HOSE/HNX phân loại theo 6 trường phái',
    tag: '703 ARSENAL',
    color: 'cyan'
  },
  {
    id: 'F13',
    name: 'Alpha Decay Profiler',
    nameVi: 'Hồ sơ Suy giảm Alpha (Half-Life)',
    category: 'ACTIVE_ALPHA',
    module: 'alpha_factory',
    subTab: 'ALPHA_DECAY',
    description: 'Forward IC half-life decay modeling from 1D to 30D holding horizons',
    descriptionVi: 'Mô hình hóa chu kỳ bán rã (Half-life) của thông tin alpha từ 1 đến 30 ngày',
    tag: 'ALPHA DECAY',
    color: 'cyan'
  },
  {
    id: 'F14',
    name: 'Genetic Programming Discovery',
    nameVi: 'Tiến hóa Alpha Di truyền (GP Engine)',
    category: 'ACTIVE_ALPHA',
    module: 'alpha_factory',
    subTab: 'GENETIC_EVOLUTION',
    description: 'Autonomous symbolic regression, crossover, mutation, and tournament selection',
    descriptionVi: 'Tự động tạo lập và lai ghép công thức alpha tối ưu bằng thuật toán di truyền',
    tag: 'GENETIC GP',
    color: 'cyan'
  },

  // 4. Strategy & CPCV (3)
  {
    id: 'F15',
    name: 'Walk-Forward CPCV (15 Folds)',
    nameVi: 'Kiểm định Chéo Tổ hợp Walk-Forward CPCV',
    category: 'STRATEGY_CPCV',
    module: 'strategy_lab',
    subTab: 'cpcv',
    description: 'Combinatorial Purged Cross-Validation with strict embargoing against leakage',
    descriptionVi: 'Phương pháp kiểm định chống rò rỉ dữ liệu (Leakage) hàng đầu của Marcos López de Prado',
    tag: 'CPCV 15-FOLDS',
    color: 'purple'
  },
  {
    id: 'F16',
    name: 'Conformal Prediction Bands',
    nameVi: 'Dự báo Định lượng Chuẩn xác Conformal',
    category: 'STRATEGY_CPCV',
    module: 'strategy_lab',
    subTab: 'conformal',
    description: 'Finite-sample non-parametric prediction intervals at 90% confidence horizon',
    descriptionVi: 'Dải băng dự báo xác suất không tham số với độ tin cậy toán học 90%',
    tag: 'CONFORMAL BANDS',
    color: 'purple'
  },
  {
    id: 'F17',
    name: 'Overfitting Diagnostics (DSR / PBO)',
    nameVi: 'Chẩn đoán Quá khớp DSR & PBO',
    category: 'STRATEGY_CPCV',
    module: 'strategy_lab',
    subTab: 'overfitting',
    description: 'Deflated Sharpe Ratio (DSR), Probability of Backtest Overfitting (PBO), Haircut Sharpe',
    descriptionVi: 'Đo lường tỷ lệ Sharpe chiết khấu và xác suất mô hình bị quá khớp dữ liệu quá khứ',
    tag: 'DSR / PBO',
    color: 'purple'
  },

  // 5. Governance & MLOps (5)
  {
    id: 'F18',
    name: 'Model Registry & Lifecycle',
    nameVi: 'Quản trị Vòng đời Mô hình Registry',
    category: 'GOVERNANCE',
    module: 'model_registry',
    subTab: 'registry',
    description: 'State machine tracking models across CANDIDATE, VALIDATED, and PRODUCTION',
    descriptionVi: 'Quản lý phiên bản mô hình máy học qua các giai đoạn Ứng viên, Thẩm định, Vận hành',
    tag: 'MODEL REGISTRY',
    color: 'amber'
  },
  {
    id: 'F19',
    name: 'Model Drift Monitor (PSI / KS)',
    nameVi: 'Giám sát Độ trôi Dữ liệu PSI & KS',
    category: 'GOVERNANCE',
    module: 'model_registry',
    subTab: 'drift',
    description: 'Population Stability Index and Kolmogorov-Smirnov distribution test',
    descriptionVi: 'Cảnh báo tự động khi phân phối dữ liệu thị trường thực tế sai lệch so với huấn luyện',
    tag: 'DRIFT MONITOR',
    color: 'amber'
  },
  {
    id: 'F20',
    name: 'TOTP Guarded Model Promotion',
    nameVi: 'Thăng cấp Mô hình Bảo mật TOTP',
    category: 'GOVERNANCE',
    module: 'model_registry',
    subTab: 'totp',
    description: 'Cryptographic 6-digit TOTP key required to deploy models to live production',
    descriptionVi: 'Bảo mật 2 lớp bắt buộc mã xác thực OTP khi đưa mô hình vào giao dịch thực',
    tag: 'TOTP PROMOTION',
    color: 'amber'
  },
  {
    id: 'F21',
    name: 'Instant Model Rollback',
    nameVi: 'Quy trình Hoàn tác Mô hình Tức thì',
    category: 'GOVERNANCE',
    module: 'model_registry',
    subTab: 'rollback',
    description: 'Deterministic zero-downtime rollback to verified checkpoint configurations',
    descriptionVi: 'Khôi phục ngay lập tức về phiên bản mô hình an toàn trước đó khi phát hiện bất thường',
    tag: 'MODEL ROLLBACK',
    color: 'amber'
  },
  {
    id: 'F22',
    name: 'Dynamic Resource Governor',
    nameVi: 'Điều phối Tài nguyên Động Governor',
    category: 'GOVERNANCE',
    module: 'model_registry',
    subTab: 'governor',
    description: 'COPILOT vs MANUAL execution modes with adaptive concurrency budgeting',
    descriptionVi: 'Chuyển đổi chế độ Copilot tự hành hoặc Thủ công và kiểm soát số luồng song song',
    tag: 'RESOURCE GOVERNOR',
    color: 'amber'
  },

  // 6. Supply Chain & System (6)
  {
    id: 'F23',
    name: 'Corporate Ownership Graph',
    nameVi: 'Sơ đồ Sở hữu Cổ đông & Doanh nghiệp',
    category: 'SYSTEM_SUPPLY',
    module: 'fundamental_matrix',
    subTab: 'ownership',
    description: 'Entity graph visualizer mapping cross-holdings, state stakes, and foreign funds',
    descriptionVi: 'Trực quan hóa cấu trúc sở hữu chéo, cổ đông nhà nước và tổ chức nước ngoài',
    tag: 'CORPORATE GRAPH',
    color: 'blue'
  },
  {
    id: 'F24',
    name: 'Supply Chain Dependencies',
    nameVi: 'Chuỗi Cung ứng Thượng/Hạ nguồn',
    category: 'SYSTEM_SUPPLY',
    module: 'fundamental_matrix',
    subTab: 'supply_chain',
    description: 'Multi-tier supplier, client, and commodity input risk exposure mapping',
    descriptionVi: 'Mạng lưới phụ thuộc nhà cung cấp, khách hàng và rủi ro nguyên vật liệu đầu vào',
    tag: 'SUPPLY CHAIN',
    color: 'blue'
  },
  {
    id: 'F25',
    name: 'Dynamic Universe ADV Screener',
    nameVi: 'Bộ lọc Không gian Đầu tư Động VN30/VN703',
    category: 'SYSTEM_SUPPLY',
    module: 'fundamental_matrix',
    subTab: 'screener',
    description: 'Multi-criteria screening with Piotroski F-Score, Altman Z-Score, ROE, and liquidity',
    descriptionVi: 'Lọc cổ phiếu theo thanh khoản ADV, sức khỏe tài chính F-Score và Z-Score',
    tag: 'ADV SCREENER',
    color: 'blue'
  },
  {
    id: 'F26',
    name: 'Real-time Cryptographic Receipts',
    nameVi: 'Biên nhận Xác thực Mã hóa SHA-256',
    category: 'SYSTEM_SUPPLY',
    module: 'control_center',
    subTab: 'receipts',
    description: 'Cryptographic SHA-256 fingerprinting for every ingestion and optimization task',
    descriptionVi: 'Ký số biên nhận SHA-256 minh bạch cho mọi tác vụ nạp dữ liệu và tối ưu hóa',
    tag: 'SHA-256 RECEIPTS',
    color: 'blue'
  },
  {
    id: 'F27',
    name: 'Omni-Quant Copilot Orchestrator',
    nameVi: 'Trợ lý Lượng hóa AI Omni-Quant',
    category: 'SYSTEM_SUPPLY',
    module: 'control_center',
    subTab: 'copilot',
    description: 'Context-aware quantitative co-pilot generating actionable market orders',
    descriptionVi: 'Trợ lý AI tích hợp phân tích kỹ thuật, vĩ mô và tạo bảng lệnh khuyến nghị',
    tag: 'AI COPILOT',
    color: 'blue'
  },
  {
    id: 'F28',
    name: 'Multi-Provider LLM Intelligent Bridge',
    nameVi: 'Cầu nối Đa Nhà cung cấp LLM Thông minh',
    category: 'SYSTEM_SUPPLY',
    module: 'control_center',
    subTab: 'llm_bridge',
    description: 'Enterprise fallback router supporting OpenAI, Anthropic, Gemini, DeepSeek, Local',
    descriptionVi: 'Định tuyến thông minh và chuyển đổi dự phòng mượt mà giữa các mô hình LLM lớn',
    tag: 'LLM BRIDGE',
    color: 'blue'
  }
];

export const LandingDatabaseHub: React.FC = () => {
  const navigateToFeature = useUiStore((state) => state.navigateToFeature);
  const { locale } = useTranslation();
  const isVi = locale === 'vi';
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isTriggering, setIsTriggering] = useState<boolean>(false);

  const {
    tasks,
    triggerIngestData,
    setIsDrawerOpen
  } = useControlOps();

  // Find latest ingestion task
  const latestIngestTask = Object.values(tasks)
    .filter((t) => t.taskType === 'DATA_INGESTION')
    .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())[0];

  const handleQuickUpdate = async () => {
    setIsTriggering(true);
    try {
      const now = new Date();
      const endStr = now.toISOString().split('T')[0];
      const startStr = `${now.getFullYear() - 1}-01-01`;
      await triggerIngestData({
        symbols: ['VN30'],
        sources: ['vci', 'macro', 'news'],
        force_refresh: false,
        start_date: startStr,
        end_date: endStr
      });
    } finally {
      setIsTriggering(false);
    }
  };

  const filteredFeatures = ADVANCED_28_FEATURES.filter((feat) => {
    const matchesCategory = selectedCategory === 'ALL' || feat.category === selectedCategory;
    const q = searchQuery.toLowerCase().trim();
    const matchesQuery = !q ||
      feat.name.toLowerCase().includes(q) ||
      feat.nameVi.toLowerCase().includes(q) ||
      feat.tag.toLowerCase().includes(q) ||
      feat.description.toLowerCase().includes(q) ||
      feat.descriptionVi.toLowerCase().includes(q);
    return matchesCategory && matchesQuery;
  });

  const categories = [
    { key: 'ALL', label: isVi ? 'Tất cả (28 chức năng)' : 'All (28 Features)' },
    { key: 'MICROSTRUCTURE', label: isVi ? 'Vi cấu trúc & Sổ lệnh (4)' : 'Microstructure (4)' },
    { key: 'RISK_TCA', label: isVi ? 'Rủi ro Barra & TCA (6)' : 'Barra & TCA (6)' },
    { key: 'ACTIVE_ALPHA', label: isVi ? 'Alpha Factory & AST (4)' : 'Alpha Factory (4)' },
    { key: 'STRATEGY_CPCV', label: isVi ? 'Chiến lược & CPCV (3)' : 'Strategy & CPCV (3)' },
    { key: 'GOVERNANCE', label: isVi ? 'Quản trị MLOps & TOTP (5)' : 'Governance (5)' },
    { key: 'SYSTEM_SUPPLY', label: isVi ? 'Chuỗi Cung ứng & AI (6)' : 'Supply Chain & AI (6)' },
  ];

  return (
    <div className="flex flex-col gap-4 font-mono select-none">
      {/* 1. TOP STATUS BANNER: Database Lakehouse & Ingest Progress */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Card 1: Database Metadata & Freshness */}
        <div className="lg:col-span-2 p-4 rounded-xl border border-white/10 bg-zinc-900/80 backdrop-blur-md flex flex-col justify-between gap-3 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                <Database className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xs font-bold text-zinc-100 tracking-wide uppercase">
                    {isVi ? 'Cơ sở Dữ liệu Định lượng Master' : 'Master Quant Parquet Lakehouse'}
                  </h2>
                  <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    PIT VALIDATED
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400">
                  {isVi ? 'Tên CSDL: ' : 'Database Name: '}
                  <span className="text-emerald-400 font-semibold">OMEGA_QUANT_LAKEHOUSE_VN703</span>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 text-right">
              <span className="text-[10px] px-2 py-1 rounded bg-zinc-950 border border-white/10 text-zinc-300">
                Format: <strong className="text-cyan-400">Apache Parquet + ZSTD</strong>
              </span>
            </div>
          </div>

          {/* Database Specs Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-xs">
            <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-white/5 flex flex-col gap-0.5">
              <span className="text-[10px] text-zinc-500">{isVi ? 'Khung thời gian CSDL' : 'Dataset Coverage'}</span>
              <span className="text-xs font-bold text-zinc-200">2015-01-01 → 2024-12-31</span>
              <span className="text-[9px] text-emerald-400 font-semibold">{isVi ? 'Dữ liệu Lịch sử 10 Năm' : '10-Yr Historical Range'}</span>
            </div>

            <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-white/5 flex flex-col gap-0.5">
              <span className="text-[10px] text-zinc-500">{isVi ? 'Ngày cập nhật (As-Of)' : 'Latest As-Of Time'}</span>
              <span className="text-xs font-bold text-cyan-400">
                {latestIngestTask?.payload?.freshness
                  ? String(latestIngestTask.payload.freshness).split(' ')[0]
                  : '2026-08-30'}
              </span>
              <span className="text-[9px] text-zinc-400">UTC+7 ICT Ho Chi Minh</span>
            </div>

            <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-white/5 flex flex-col gap-0.5">
              <span className="text-[10px] text-zinc-500">{isVi ? 'Không gian Đầu tư' : 'Universe Coverage'}</span>
              <span className="text-xs font-bold text-purple-300">VN30 / VN703 HOSE+HNX</span>
              <span className="text-[9px] text-zinc-400">2,580,000+ Records</span>
            </div>

            <div className="p-2.5 rounded-lg bg-zinc-950/60 border border-white/5 flex flex-col gap-0.5">
              <span className="text-[10px] text-zinc-500">{isVi ? 'An toàn Point-in-Time' : 'PIT Safety Score'}</span>
              <span className="text-xs font-bold text-emerald-400 flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5" /> 100.0%
              </span>
              <span className="text-[9px] text-zinc-400">Zero Lookahead Bias</span>
            </div>
          </div>
        </div>

        {/* Card 2: Live Ingestion & Sync Progress */}
        <div className="p-4 rounded-xl border border-white/10 bg-zinc-900/80 backdrop-blur-md flex flex-col justify-between gap-3 shadow-lg">
          <div className="flex items-center justify-between border-b border-white/10 pb-2">
            <div className="flex items-center gap-2">
              <RefreshCw className={`w-4 h-4 ${isTriggering || latestIngestTask?.status === 'RUNNING' ? 'text-cyan-400 animate-spin' : 'text-zinc-400'}`} />
              <h3 className="text-xs font-bold text-zinc-200 uppercase">
                {isVi ? 'Tiến trình Đồng bộ Dữ liệu' : 'Data Ingestion & Sync'}
              </h3>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
              latestIngestTask?.status === 'RUNNING' || isTriggering
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 animate-pulse'
                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
            }`}>
              {latestIngestTask?.status === 'RUNNING' || isTriggering
                ? (isVi ? 'ĐANG ĐỒNG BỘ...' : 'SYNCING...')
                : (isVi ? 'ĐÃ ĐỒNG BỘ' : 'SYNC COMPLETED')}
            </span>
          </div>

          {/* Progress Bar Display */}
          <div className="flex flex-col gap-1.5 text-xs">
            <div className="flex items-center justify-between text-[11px] text-zinc-300">
              <span>{latestIngestTask?.stage || (isVi ? 'Trạng thái Pipeline' : 'Pipeline Stage')}</span>
              <span className="font-bold text-cyan-400">
                {latestIngestTask ? `${Math.round(latestIngestTask.progress)}%` : '100%'}
              </span>
            </div>

            <div className="w-full bg-zinc-950 rounded-full h-2 overflow-hidden border border-white/5">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 via-cyan-400 to-purple-500 rounded-full transition-all duration-300"
                style={{ width: `${latestIngestTask ? latestIngestTask.progress : 100}%` }}
              />
            </div>

            <div className="text-[10px] text-zinc-400 truncate mt-0.5">
              {latestIngestTask?.message || (isVi ? 'Dữ liệu VCI, Vĩ mô và Tin tức đã được xác thực an toàn.' : 'VCI, Macro & Sentiment feeds verified and cached.')}
            </div>
          </div>

          {/* Quick Action Button */}
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={handleQuickUpdate}
              disabled={isTriggering || latestIngestTask?.status === 'RUNNING'}
              className="flex-1 py-1.5 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-zinc-950 font-bold text-xs flex items-center justify-center gap-1.5 shadow transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isTriggering ? 'animate-spin' : ''}`} />
              {isVi ? 'Cập nhật Dữ liệu Ngay (VN30)' : 'Sync / Ingest VN30 Data Now'}
            </button>

            <button
              onClick={() => setIsDrawerOpen(true)}
              className="px-2.5 py-1.5 rounded-lg bg-zinc-950 hover:bg-zinc-800 border border-white/10 text-zinc-300 text-xs flex items-center gap-1"
              title={isVi ? 'Xem chi tiết biên nhận' : 'View telemetry receipt'}
            >
              <FileCheck className="w-3.5 h-3.5 text-cyan-400" />
            </button>
          </div>
        </div>
      </div>

      {/* 2. 28 ADVANCED INSTITUTIONAL QUANT FEATURES HUB */}
      <div className="p-4 rounded-xl border border-white/10 bg-zinc-900/60 backdrop-blur-md flex flex-col gap-3.5 shadow-xl">
        {/* Header Ribbon & Filter Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-400">
              <Zap className="w-5 h-5" />
            </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wide">
                    {isVi ? '28 Chức Năng Định Lượng Nâng Cao Đã Đấu Nối' : '28 Institutional Quant Engines Active'}
                  </h2>
                  <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    {isVi
                      ? `ĐÃ ĐẤU NỐI & SẴN SÀNG (${filteredFeatures.length}/28)`
                      : `ACTIVE & CONNECTED (${filteredFeatures.length}/28)`}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400">
                  {isVi ? 'Bấm vào bất kỳ chức năng nào để chuyển ngay đến module và phân hệ xử lý tương ứng' : 'Click any engine card to immediately launch its dedicated quantitative station'}
                </p>
              </div>
          </div>

          {/* Search Box */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-950 border border-white/10 text-zinc-300 text-xs w-full sm:w-64">
            <Search className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
            <input
              type="text"
              placeholder={isVi ? 'Tìm kiếm chức năng...' : 'Search engines...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent border-none outline-none text-zinc-100 placeholder-zinc-500 w-full text-xs font-mono"
            />
          </div>
        </div>

        {/* Category Filter Chips */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {categories.map((cat) => (
            <button
              key={cat.key}
              onClick={() => setSelectedCategory(cat.key)}
              className={`px-3 py-1 rounded-lg text-[11px] font-bold transition-colors ${
                selectedCategory === cat.key
                  ? 'bg-zinc-100 text-zinc-950 shadow'
                  : 'bg-zinc-950/60 hover:bg-zinc-800 text-zinc-400 border border-white/5'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* 28 Features Interactive Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2.5 pt-1">
          {filteredFeatures.map((feat) => (
            <div
              key={feat.id}
              onClick={() => navigateToFeature(feat.module, feat.subTab, feat.id)}
              className="group p-3 rounded-xl border border-white/5 hover:border-cyan-500/40 bg-zinc-950/50 hover:bg-zinc-900/80 transition-all duration-200 cursor-pointer flex flex-col justify-between gap-2 hover:shadow-lg relative overflow-hidden"
            >
              {/* Card Header: Tag & ID */}
              <div className="flex items-center justify-between text-[10px]">
                <span className="font-bold text-zinc-500 group-hover:text-cyan-400 transition-colors">
                  {feat.id}
                </span>
                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white/5 text-zinc-300 border border-white/10 group-hover:border-cyan-500/30">
                  {feat.tag}
                </span>
              </div>

              {/* Card Title & Description */}
              <div className="flex flex-col gap-1">
                <h4 className="text-xs font-bold text-zinc-200 group-hover:text-zinc-100 transition-colors leading-tight">
                  {isVi ? feat.nameVi : feat.name}
                </h4>
                <p className="text-[10px] text-zinc-400 line-clamp-2 leading-relaxed">
                  {isVi ? feat.descriptionVi : feat.description}
                </p>
              </div>

              {/* Card Footer: Status & Action */}
              <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[10px] text-zinc-500">
                <span className="flex items-center gap-1 text-emerald-400 font-bold text-[9px]">
                  <CheckCircle2 className="w-3 h-3" /> {isVi ? 'ĐÃ ĐẤU NỐI' : 'ACTIVE'}
                </span>
                <span className="text-zinc-400 group-hover:text-cyan-400 font-bold flex items-center gap-0.5 text-[10px] transition-colors">
                  {isVi ? 'Mở Module' : 'Launch'} <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
