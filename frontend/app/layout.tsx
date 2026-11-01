import './globals.css';
import { QueryProvider } from './query-provider';
export const metadata = { title: 'Flood Intelligence Platform', description: 'Geo-intelligent flood response workspace' };
export default function Layout({ children }: { children: React.ReactNode }) { return <html lang="en"><body><QueryProvider>{children}</QueryProvider></body></html>; }
