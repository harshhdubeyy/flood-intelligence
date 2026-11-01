import type { Config } from 'tailwindcss';
const config: Config = { content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'], theme: { extend: { colors: { ink:'#182337', canvas:'#f7f8fa', line:'#e7ebf1', brand:'#1769e0' }, boxShadow: { soft:'0 8px 24px rgba(23,37,61,.045)' } } }, plugins: [] };
export default config;
