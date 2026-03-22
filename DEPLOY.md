# 배포 가이드

## 아키텍처
- Frontend: Vercel (React/Vite)
- Backend: Railway (FastAPI + poppler)
- 비동기 처리: PDF 업로드 → job 접수 → polling → 결과 표시

## Backend (Railway)
1. https://railway.app 에서 GitHub repo 연결
2. Root directory: `backend`
3. Builder: Dockerfile
4. 환경변수:
   - `OPENAI_API_KEY`
   - `CLOVA_OCR_INVOKE_URL`
   - `CLOVA_OCR_SECRET`
   - `ALLOWED_ORIGINS=https://your-frontend.vercel.app`
   - (`POPPLER_PATH`는 설정 불필요 — Dockerfile에서 설치됨)
5. 배포 후 public URL 확인

## Frontend (Vercel)
1. https://vercel.com 에서 GitHub repo 연결
2. Root directory: `frontend`
3. Framework: Vite
4. 환경변수:
   - `VITE_API_URL=https://your-backend.railway.app`
5. 배포

## 로컬 개발
- backend: `cd backend && python -m uvicorn main:app --reload`
- frontend: `cd frontend && npm run dev`
- `.env`에 API 키와 `POPPLER_PATH` 설정 필요

## 비용 참고
- Railway: Hobby plan $5/월 + 사용량. 소규모 팀 내부 사용은 $5~15/월 예상
- Vercel: 무료 티어로 충분
- OpenAI API: PDF 1건당 약 $0.01~0.05 (페이지 수에 따라)
- CLOVA OCR: 별도 과금
