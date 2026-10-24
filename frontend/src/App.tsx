import { BrowserRouter, Route, Routes } from "react-router"
import { AppProvider } from "@/app-context"
import { Guard, RoleDirectory } from "@/components/layout"
import { HomePage } from "@/pages/home"
import { AuthPage } from "@/pages/auth"
import {
  StudentOverview,
  StudentGoal,
  StudentAssessments,
  StudentPlan,
  StudentLessons,
  StudentAssistant,
  StudentRecordPage,
} from "@/pages/student"
import {
  TeacherOverview,
  TeacherStudents,
  TeacherLessons,
  TeacherReviews,
  TeacherPreparation,
} from "@/pages/teacher"
import {
  FounderOverview,
  FounderCases,
  FounderIncidents,
  FounderApprovals,
} from "@/pages/founder"
export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/workspaces" element={<RoleDirectory />} />
          <Route path="/p01" element={<AuthPage />} />
          <Route path="/p02" element={<AuthPage register />} />
          <Route element={<Guard role="Student" />}>
            <Route path="/s1" element={<StudentOverview />} />
            <Route path="/s2" element={<StudentGoal />} />
            <Route path="/s3" element={<StudentAssessments />} />
            <Route path="/s4" element={<StudentPlan />} />
            <Route path="/s5" element={<StudentLessons />} />
            <Route path="/s6" element={<StudentAssistant />} />
            <Route path="/s8" element={<StudentRecordPage />} />
          </Route>
          <Route element={<Guard role="Teacher" />}>
            <Route path="/t1" element={<TeacherOverview />} />
            <Route path="/t2" element={<TeacherStudents />} />
            <Route path="/t3" element={<TeacherLessons />} />
            <Route path="/t4" element={<TeacherReviews />} />
            <Route path="/t5" element={<TeacherPreparation />} />
          </Route>
          <Route element={<Guard role="Founder" />}>
            <Route path="/f1" element={<FounderOverview />} />
            <Route path="/f2" element={<FounderCases />} />
            <Route path="/f3" element={<FounderIncidents />} />
            <Route path="/f4" element={<FounderApprovals />} />
          </Route>
          <Route path="*" element={<RoleDirectory />} />
        </Routes>
      </AppProvider>
    </BrowserRouter>
  )
}
