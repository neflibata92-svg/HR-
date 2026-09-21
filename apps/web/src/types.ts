export type PageId = "dashboard" | "jobs" | "candidates" | "resumes" | "settings";

export interface NavigationItem {
  id: PageId;
  label: string;
}

export const navigation: NavigationItem[] = [
  { id: "dashboard", label: "工作台" },
  { id: "jobs", label: "岗位管理" },
  { id: "candidates", label: "候选人" },
  { id: "resumes", label: "简历库" },
  { id: "settings", label: "系统设置" },
];
