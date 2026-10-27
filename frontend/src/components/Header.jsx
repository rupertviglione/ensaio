import { Link, NavLink } from "react-router-dom";
import { Plus, Library, Drama } from "lucide-react";

const navCls = ({ isActive }) =>
  `flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-colors duration-200 ${
    isActive ? "bg-amber-500/15 text-amber-400" : "text-stone-400 hover:text-stone-100 hover:bg-white/5"
  }`;

export const Header = () => (
  <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-[#0A0908]/80 backdrop-blur-xl">
    <div className="max-w-7xl mx-auto px-6 md:px-10 h-16 flex items-center justify-between">
      <Link to="/" data-testid="header-logo" className="flex items-center gap-3 group">
        <Drama className="w-6 h-6 text-amber-500 transition-transform duration-300 group-hover:-rotate-12" />
        <span className="font-serif text-2xl font-bold tracking-[0.25em] text-stone-100">ENSAIO</span>
      </Link>
      <nav className="flex items-center gap-1">
        <NavLink to="/" end className={navCls} data-testid="nav-library">
          <Library className="w-4 h-4" /> <span className="hidden sm:inline">Biblioteca</span>
        </NavLink>
        <NavLink to="/novo" className={navCls} data-testid="nav-new-script">
          <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Novo texto</span>
        </NavLink>
      </nav>
    </div>
  </header>
);
