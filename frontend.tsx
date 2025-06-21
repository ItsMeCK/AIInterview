import React, { useState, useEffect, useCallback } from 'react';
import { Briefcase, Users, FileText, Calendar, Eye, Edit3, Trash2, PlusCircle, Send, BarChart2, Settings, LogOut, ChevronRight, Search, Filter, Image as ImageIcon, AlertCircle } from 'lucide-react';

const API_BASE_URL = 'https://interview.aiagentictool.tech/api/admin'; // Adjust if your backend runs elsewhere
const FILE_SERVER_BASE_URL = 'https://interview.aiagentictool.tech'; // Base URL for serving files from backend

// --- Helper Components ---
const StatCard = ({ title, value, icon, color }) => (
  <div className={`bg-white p-6 rounded-xl shadow-lg border-l-4 ${color}`}>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-gray-500 uppercase">{title}</p>
        <p className="text-3xl font-bold text-gray-800">{value === null || value === undefined ? 0 : value}</p>
      </div>
      <div className={`p-3 rounded-full ${color.replace('border-', 'bg-').replace('indigo', 'indigo-100').replace('green', 'green-100').replace('amber', 'amber-100').replace('sky', 'sky-100')}`}>
        {icon}
      </div>
    </div>
  </div>
);

const TabButton = ({ label, isActive, onClick }) => (
  <button
    onClick={onClick}
    className={`px-4 py-2 font-medium rounded-md transition-colors text-sm sm:text-base ${
      isActive ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-indigo-100'
    }`}
  >
    {label}
  </button>
);

const Modal = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50 transition-opacity duration-300 ease-in-out">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto transform transition-all duration-300 ease-in-out scale-95 animate-modalPopIn">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xl font-semibold text-gray-800">{title}</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-2xl leading-none p-1 rounded-full hover:bg-gray-100 transition-colors">&times;</button>
        </div>
        {children}
      </div>
    </div>
  );
};

const AlertMessage = ({ message, type = 'error', onDismiss }) => {
    if (!message) return null;
    const bgColor = type === 'error' ? 'bg-red-100 border-red-400 text-red-700' : 'bg-green-100 border-green-400 text-green-700';
    return (
        <div className={`border px-4 py-3 rounded-lg relative mb-4 ${bgColor}`} role="alert">
            <strong className="font-bold">{type === 'error' ? 'Error: ' : 'Success: '}</strong>
            <span className="block sm:inline">{message}</span>
            {onDismiss && (
                <button onClick={onDismiss} className="absolute top-0 bottom-0 right-0 px-4 py-3">
                    <span className="text-xl">&times;</span>
                </button>
            )}
        </div>
    );
};


// --- Main Components ---
const DashboardOverview = ({ summaryData, isLoading }) => {
  if (isLoading) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            {[...Array(4)].map((_, i) => (
                <div key={i} className="bg-white p-6 rounded-xl shadow-lg animate-pulse">
                    <div className="h-6 bg-gray-200 rounded w-3/4 mb-2"></div>
                    <div className="h-10 bg-gray-300 rounded w-1/2"></div>
                </div>
            ))}
        </div>
    );
  }
  if (!summaryData) {
    return <div className="text-center p-4 text-gray-500">Could not load summary data.</div>;
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      <StatCard title="Open Positions" value={summaryData.open_positions} icon={<Briefcase className="h-8 w-8 text-indigo-500" />} color="border-indigo-500" />
      <StatCard title="Total Applications" value={summaryData.total_applications} icon={<Users className="h-8 w-8 text-green-500" />} color="border-green-500" />
      <StatCard title="Interviews Scheduled" value={summaryData.interviews_scheduled} icon={<Calendar className="h-8 w-8 text-amber-500" />} color="border-amber-500" />
      <StatCard title="Pending Reviews" value={summaryData.pending_reviews} icon={<FileText className="h-8 w-8 text-sky-500" />} color="border-sky-500" />
    </div>
  );
};

const JobList = ({ jobs, onSelectJob, onAddNewJob, onDeleteJob, onEditJob, isLoading }) => {
    if (isLoading && jobs.length === 0) {
        return <div className="bg-white p-6 rounded-xl shadow-lg"><div className="animate-pulse h-8 bg-gray-200 rounded w-1/4 mb-4"></div><div className="h-40 bg-gray-100 rounded"></div></div>;
    }
    return (
      <div className="bg-white p-6 rounded-xl shadow-lg">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-800 mb-2 sm:mb-0">Job Postings</h2>
          <button onClick={onAddNewJob} className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 flex items-center transition-colors text-sm">
            <PlusCircle size={18} className="mr-2" /> Add New Job
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="p-3 text-sm font-semibold text-gray-600">Title</th>
                <th className="p-3 text-sm font-semibold text-gray-600 hidden md:table-cell">Department</th>
                <th className="p-3 text-sm font-semibold text-gray-600">Status</th>
                <th className="p-3 text-sm font-semibold text-gray-600 hidden lg:table-cell">Applications</th>
                <th className="p-3 text-sm font-semibold text-gray-600 hidden md:table-cell">Created At</th>
                <th className="p-3 text-sm font-semibold text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 && !isLoading && <tr><td colSpan={6} className="p-3 text-center text-gray-500">No jobs found.</td></tr>}
              {jobs.map(job => (
                <tr key={job.id} className="border-b hover:bg-gray-50">
                  <td className="p-3 text-gray-700 font-medium">{job.title}</td>
                  <td className="p-3 text-gray-700 hidden md:table-cell">{job.department}</td>
                  <td className="p-3">
                    <span className={`px-2 py-1 text-xs font-semibold rounded-full ${job.status === 'Open' ? 'bg-green-100 text-green-700' : job.status === 'Closed' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'}`}>
                      {job.status}
                    </span>
                  </td>
                  <td className="p-3 text-gray-700 hidden lg:table-cell">{job.applications_count || 0}</td>
                  <td className="p-3 text-gray-700 hidden md:table-cell">{job.created_at ? new Date(job.created_at).toLocaleDateString() : 'N/A'}</td>
                  <td className="p-3">
                    <div className="flex space-x-1 sm:space-x-2">
                        <button onClick={() => onSelectJob(job)} title="View Job" className="p-1 sm:p-2 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-100 rounded-md transition-colors"><Eye size={18} /></button>
                        <button onClick={() => onEditJob(job)} title="Edit Job" className="p-1 sm:p-2 text-yellow-600 hover:text-yellow-800 hover:bg-yellow-100 rounded-md transition-colors"><Edit3 size={18} /></button>
                        <button onClick={() => onDeleteJob(job.id)} title="Delete Job" className="p-1 sm:p-2 text-red-600 hover:text-red-800 hover:bg-red-100 rounded-md transition-colors"><Trash2 size={18} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
};

const InterviewList = ({ interviews, onSelectInterview, isLoading }) => {
    if (isLoading && interviews.length === 0) {
        return <div className="bg-white p-6 rounded-xl shadow-lg mt-8"><div className="animate-pulse h-8 bg-gray-200 rounded w-1/4 mb-4"></div><div className="h-40 bg-gray-100 rounded"></div></div>;
    }
    return (
      <div className="bg-white p-6 rounded-xl shadow-lg mt-8">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">Recent Interviews</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="p-3 text-sm font-semibold text-gray-600">Candidate</th>
                <th className="p-3 text-sm font-semibold text-gray-600 hidden md:table-cell">Job Title</th>
                <th className="p-3 text-sm font-semibold text-gray-600 hidden sm:table-cell">Date</th>
                <th className="p-3 text-sm font-semibold text-gray-600">Status</th>
                <th className="p-3 text-sm font-semibold text-gray-600 hidden lg:table-cell">Score</th>
                <th className="p-3 text-sm font-semibold text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {interviews.length === 0 && !isLoading && <tr><td colSpan={6} className="p-3 text-center text-gray-500">No interviews found.</td></tr>}
              {interviews.map(interview => (
                <tr key={interview.id} className="border-b hover:bg-gray-50">
                  <td className="p-3 text-gray-700 font-medium">{interview.candidate_name || 'N/A'}</td>
                  <td className="p-3 text-gray-700 hidden md:table-cell">{interview.job_title || 'N/A'}</td>
                  <td className="p-3 text-gray-700 hidden sm:table-cell">{interview.interview_date ? new Date(interview.interview_date).toLocaleDateString() : 'N/A'}</td>
                  <td className="p-3">
                    <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                      interview.status === 'Scheduled' ? 'bg-blue-100 text-blue-700' :
                      interview.status === 'Completed' ? 'bg-green-100 text-green-700' :
                      interview.status === 'Pending Review' ? 'bg-yellow-100 text-yellow-700' :
                      interview.status === 'Reviewed' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-700'
                    }`}>
                      {interview.status}
                    </span>
                  </td>
                  <td className="p-3 text-gray-700 hidden lg:table-cell">{interview.score !== null ? `${interview.score}/100` : 'N/A'}</td>
                  <td className="p-3">
                    <button onClick={() => onSelectInterview(interview.id)} title="View Interview" className="p-1 sm:p-2 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-100 rounded-md transition-colors"><Eye size={18} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
};

const JobDetailView = ({ job, interviewsForJob, onBack, onSelectInterview, onEditJob, onSendInvites, isLoading }) => {
  if (isLoading) return <div className="bg-white p-6 rounded-xl shadow-lg animate-pulse"><div className="h-8 bg-gray-200 rounded w-1/2 mb-4"></div><div className="h-6 bg-gray-200 rounded w-1/3 mb-2"></div><div className="h-40 bg-gray-100 rounded mb-6"></div><div className="h-10 bg-gray-200 rounded w-1/4"></div></div>;
  if (!job) return <div className="p-6 text-center text-gray-500">Job details not found or could not be loaded.</div>;

  return (
    <div className="bg-white p-6 rounded-xl shadow-lg">
      <button onClick={onBack} className="mb-4 text-indigo-600 hover:text-indigo-800 flex items-center text-sm">
        &larr; Back to Dashboard
      </button>
      <h2 className="text-2xl font-bold text-gray-800 mb-2">{job.title}</h2>
      <p className="text-gray-600 mb-1">Department: {job.department}</p>
      <p className="text-gray-600 mb-4">Status: <span className={`font-semibold ${job.status === 'Open' ? 'text-green-600' : job.status === 'Closed' ? 'text-red-600' : 'text-yellow-600'}`}>{job.status}</span></p>

      <div className="mb-6 p-4 border rounded-lg bg-gray-50">
        <h3 className="text-lg font-semibold text-gray-700 mb-2">Job Description</h3>
        <p className="text-gray-600 whitespace-pre-wrap text-sm">{job.description || "No description provided."}</p>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        <button onClick={() => onEditJob(job)} className="bg-yellow-500 text-white px-4 py-2 rounded-lg hover:bg-yellow-600 flex items-center transition-colors text-sm">
          <Edit3 size={16} className="mr-2" /> Edit Job
        </button>
        <button onClick={() => onSendInvites(job.id)} className="bg-sky-500 text-white px-4 py-2 rounded-lg hover:bg-sky-600 flex items-center transition-colors text-sm">
          <Send size={16} className="mr-2" /> Send Invites
        </button>
      </div>

      <h3 className="text-xl font-semibold text-gray-800 mb-4">Interviews for this Job ({interviewsForJob.length})</h3>
      {interviewsForJob.length > 0 ? (
        <InterviewList interviews={interviewsForJob} onSelectInterview={onSelectInterview} isLoading={isLoading} />
      ) : (
        <p className="text-gray-500 text-sm">No interviews scheduled for this job yet.</p>
      )}
    </div>
  );
};

const InterviewDetailView = ({ interviewDetails, onBack, onSaveFeedback, isLoading }) => {
  const [activeTab, setActiveTab] = useState('Transcript');
  const [score, setScore] = useState('');
  const [feedback, setFeedback] = useState('');

  useEffect(() => {
    if (interviewDetails) {
      setScore(interviewDetails.score !== null && interviewDetails.score !== undefined ? String(interviewDetails.score) : '');
      setFeedback(interviewDetails.admin_feedback || '');
    } else {
      setScore('');
      setFeedback('');
    }
  }, [interviewDetails]);

  if (isLoading) return <div className="bg-white p-6 rounded-xl shadow-lg animate-pulse"><div className="h-8 bg-gray-200 rounded w-1/2 mb-4"></div><div className="h-6 bg-gray-200 rounded w-1/3 mb-2"></div><div className="h-60 bg-gray-100 rounded"></div></div>;
  if (!interviewDetails) return <div className="p-6 text-center text-gray-500">Interview details not found or could not be loaded.</div>;


  const handleSave = () => {
    const scoreValue = score.trim() === '' ? null : parseInt(score, 10);
    if (score.trim() !== '' && (isNaN(scoreValue) || scoreValue < 0 || scoreValue > 100)) {
        alert("Score must be a number between 0 and 100, or left blank.");
        return;
    }
    onSaveFeedback(interviewDetails.id, scoreValue, feedback);
  };

  const screenshotPaths = Array.isArray(interviewDetails.screenshots) ? interviewDetails.screenshots : [];

  return (
    <div className="bg-white p-6 rounded-xl shadow-lg">
      <button onClick={onBack} className="mb-4 text-indigo-600 hover:text-indigo-800 flex items-center text-sm">
        &larr; Back
      </button>
      <div className="md:flex justify-between items-start mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-800 mb-1">{interviewDetails.candidate_name || 'N/A'}</h2>
          <p className="text-gray-600 mb-1 text-sm">For: {interviewDetails.job_title || 'N/A'}</p>
          <p className="text-gray-600 text-sm">Date: {interviewDetails.interview_date ? new Date(interviewDetails.interview_date).toLocaleString() : 'N/A'}</p>
        </div>
        <div className="mt-4 md:mt-0 text-right">
            <p className="text-md font-semibold text-gray-700">Status: <span className={`px-2 py-1 text-xs rounded-full ${
                    interviewDetails.status === 'Scheduled' ? 'bg-blue-100 text-blue-700' :
                    interviewDetails.status === 'Completed' ? 'bg-green-100 text-green-700' :
                    interviewDetails.status === 'Pending Review' ? 'bg-yellow-100 text-yellow-700' :
                    interviewDetails.status === 'Reviewed' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-700'
                  }`}>{interviewDetails.status}</span></p>
            {interviewDetails.score !== null && interviewDetails.score !== undefined && <p className="text-2xl font-bold text-indigo-600 mt-1">Score: {interviewDetails.score}/100</p>}
        </div>
      </div>

      <div className="border-b border-gray-200 mb-6">
        <nav className="flex space-x-1 sm:space-x-2 -mb-px flex-wrap">
          <TabButton label="Transcript" isActive={activeTab === 'Transcript'} onClick={() => setActiveTab('Transcript')} />
          <TabButton label="AI Questions" isActive={activeTab === 'AI Questions'} onClick={() => setActiveTab('AI Questions')} />
          <TabButton label="Summary" isActive={activeTab === 'Summary'} onClick={() => setActiveTab('Summary')} />
          <TabButton label="Screenshots" isActive={activeTab === 'Screenshots'} onClick={() => setActiveTab('Screenshots')} />
          <TabButton label="Scoring" isActive={activeTab === 'Scoring & Feedback'} onClick={() => setActiveTab('Scoring & Feedback')} />
        </nav>
      </div>

      <div className="min-h-[300px]"> {/* Ensure content area has min height */}
        {activeTab === 'Transcript' && (
          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Full Transcript</h3>
            <pre className="bg-gray-50 p-4 rounded-lg text-sm text-gray-700 whitespace-pre-wrap h-96 overflow-y-auto">{interviewDetails.transcript || "No transcript available."}</pre>
          </div>
        )}
        {activeTab === 'AI Questions' && (
          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Questions Asked by AI</h3>
            {(interviewDetails.questions && Array.isArray(interviewDetails.questions) && interviewDetails.questions.length > 0) ? (
              <ul className="space-y-4">
                {interviewDetails.questions.map((item, index) => (
                  <li key={index} className="p-3 border rounded-lg bg-gray-50">
                    <p className="font-medium text-indigo-600 text-sm">Q{index + 1}: {item.q}</p>
                    <p className="text-gray-700 mt-1 text-sm">A: {item.a}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="text-gray-500 text-sm">No AI questions recorded.</p>}
          </div>
        )}
        {activeTab === 'Summary' && (
          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-2">AI Generated Summary</h3>
            <p className="bg-gray-50 p-4 rounded-lg text-gray-700 whitespace-pre-wrap text-sm">{interviewDetails.summary || "No summary available."}</p>
          </div>
        )}
        {activeTab === 'Screenshots' && (
          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Candidate Screenshots</h3>
            {(screenshotPaths.length > 0) ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                {screenshotPaths.map((srcPath, index) => (
                  <img
                    key={index}
                    src={`${FILE_SERVER_BASE_URL}${srcPath.startsWith('/') ? '' : '/'}${srcPath}`} // Ensure leading slash for path
                    alt={`Screenshot ${index + 1}`}
                    className="rounded-lg shadow-md object-cover w-full h-48 border"
                    onError={(e) => { (e.target as HTMLImageElement).onerror = null; (e.target as HTMLImageElement).src="https://placehold.co/300x200/CCCCCC/FFFFFF?text=Image+Error"; }}/>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 px-4 border-2 border-dashed border-gray-300 rounded-lg">
                <ImageIcon className="mx-auto h-12 w-12 text-gray-400" />
                <h3 className="mt-2 text-sm font-medium text-gray-900">No Screenshots Available</h3>
                <p className="mt-1 text-sm text-gray-500">Screenshots taken during the interview will appear here.</p>
              </div>
            )}
          </div>
        )}
        {activeTab === 'Scoring & Feedback' && (
          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Scoring & Admin Feedback</h3>
            <div className="space-y-4">
              <div>
                <label htmlFor="score" className="block text-sm font-medium text-gray-700">Overall Score (0-100)</label>
                <input type="number" id="score" name="score" value={score} onChange={(e) => setScore(e.target.value)} className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="Enter score (optional)"/>
              </div>
              <div>
                <label htmlFor="feedback" className="block text-sm font-medium text-gray-700">Admin Feedback/Notes</label>
                <textarea id="feedback" name="feedback" rows="4" value={feedback} onChange={(e) => setFeedback(e.target.value)} className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="Enter your feedback..."></textarea>
              </div>
              <button onClick={handleSave} className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 transition-colors text-sm">Save Feedback</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const JobFormModal = ({ isOpen, onClose, onSaveJob, jobToEdit }) => {
  const [title, setTitle] = useState('');
  const [department, setDepartment] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState('Open');
  const [formError, setFormError] = useState('');


  useEffect(() => {
    if (isOpen) { // Only update form when modal becomes visible or jobToEdit changes
        if (jobToEdit) {
            setTitle(jobToEdit.title || '');
            setDepartment(jobToEdit.department || '');
            setDescription(jobToEdit.description || '');
            setStatus(jobToEdit.status || 'Open');
        } else {
            setTitle('');
            setDepartment('');
            setDescription('');
            setStatus('Open');
        }
        setFormError(''); // Clear previous errors
    }
  }, [jobToEdit, isOpen]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');
    if (!title.trim() || !department.trim() || !description.trim()) {
        setFormError("Please fill all required fields: Title, Department, Description.");
        return;
    }
    const jobData = { title, department, description, status };
    onSaveJob(jobData, jobToEdit ? jobToEdit.id : null);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={jobToEdit ? "Edit Job Posting" : "Add New Job Posting"}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {formError && <AlertMessage message={formError} type="error" onDismiss={() => setFormError('')} />}
        <div>
          <label htmlFor="jobTitle" className="block text-sm font-medium text-gray-700">Job Title</label>
          <input type="text" id="jobTitle" value={title} onChange={(e) => setTitle(e.target.value)} required className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" />
        </div>
        <div>
          <label htmlFor="department" className="block text-sm font-medium text-gray-700">Department</label>
          <input type="text" id="department" value={department} onChange={(e) => setDepartment(e.target.value)} required className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" />
        </div>
        <div>
          <label htmlFor="jobDescription" className="block text-sm font-medium text-gray-700">Job Description</label>
          <textarea id="jobDescription" value={description} onChange={(e) => setDescription(e.target.value)} rows="5" required className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="Enter full job description, responsibilities, qualifications..."></textarea>
        </div>
        <div>
          <label htmlFor="jobStatus" className="block text-sm font-medium text-gray-700">Status</label>
          <select id="jobStatus" value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
            <option value="Open">Open</option>
            <option value="Closed">Closed</option>
            <option value="Draft">Draft</option>
          </select>
        </div>
        <div className="flex justify-end space-x-3 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors">Cancel</button>
          <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 transition-colors">{jobToEdit ? "Save Changes" : "Add Job"}</button>
        </div>
      </form>
    </Modal>
  );
};


// --- Main App Component ---
const App = () => {
  const [isLoggedIn, setIsLoggedIn] = useState(true);
  const [userId, setUserId] = useState("admin_demo_user");

  const [jobs, setJobs] = useState([]);
  const [interviews, setInterviews] = useState([]); // Can hold all or filtered interviews
  const [dashboardSummary, setDashboardSummary] = useState(null);

  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedJobDetails, setSelectedJobDetails] = useState(null);
  const [selectedInterviewId, setSelectedInterviewId] = useState(null);
  const [selectedInterviewDetails, setSelectedInterviewDetails] = useState(null);

  const [isJobFormModalOpen, setIsJobFormModalOpen] = useState(false);
  const [editingJob, setEditingJob] = useState(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isLoading, setIsLoading] = useState({
    dashboard: true, jobs: true, interviews: true, jobDetails: false, interviewDetails: false
  });
  const [globalError, setGlobalError] = useState(null);

  const setLoadingState = (key, value) => setIsLoading(prev => ({ ...prev, [key]: value }));

  // --- Data Fetching Functions ---
  const fetchDashboardSummary = useCallback(async () => {
    setLoadingState('dashboard', true);
    try {
      const response = await fetch(`${API_BASE_URL}/dashboard-summary`);
      if (!response.ok) throw new Error(`HTTP error ${response.status} fetching summary`);
      const data = await response.json();
      setDashboardSummary(data);
      setGlobalError(null);
    } catch (err) {
      console.error("Failed to fetch dashboard summary:", err);
      setGlobalError(err.message);
      setDashboardSummary(null);
    } finally {
      setLoadingState('dashboard', false);
    }
  }, []);

  const fetchJobs = useCallback(async () => {
    setLoadingState('jobs', true);
    try {
      const response = await fetch(`${API_BASE_URL}/jobs`);
      if (!response.ok) throw new Error(`HTTP error ${response.status} fetching jobs`);
      const data = await response.json();
      setJobs(data);
      setGlobalError(null);
    } catch (err) {
      console.error("Failed to fetch jobs:", err);
      setGlobalError(err.message);
      setJobs([]);
    } finally {
      setLoadingState('jobs', false);
    }
  }, []);

  const fetchInterviewsForDashboard = useCallback(async () => {
    setLoadingState('interviews', true);
    try {
      const response = await fetch(`${API_BASE_URL}/interviews`); // Fetches all for dashboard
      if (!response.ok) throw new Error(`HTTP error ${response.status} fetching interviews`);
      const data = await response.json();
      setInterviews(data);
      setGlobalError(null);
    } catch (err) {
      console.error("Failed to fetch interviews for dashboard:", err);
      setGlobalError(err.message);
      setInterviews([]);
    } finally {
      setLoadingState('interviews', false);
    }
  }, []);

  const fetchJobDetailsAndInterviews = useCallback(async (jobId) => {
    if (!jobId) {
        setSelectedJobDetails(null);
        setInterviews([]); // Clear interviews if no job selected
        return;
    }
    setLoadingState('jobDetails', true);
    setLoadingState('interviews', true); // Also loading interviews for this job
    try {
        const jobResponse = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
        if (!jobResponse.ok) {
            if(jobResponse.status === 404) setSelectedJobDetails(null);
            throw new Error(`HTTP error ${jobResponse.status} fetching job ${jobId}`);
        }
        const jobData = await jobResponse.json();
        setSelectedJobDetails(jobData);

        const interviewsResponse = await fetch(`${API_BASE_URL}/interviews?job_id=${jobId}`);
        if(!interviewsResponse.ok) throw new Error(`HTTP error ${interviewsResponse.status} fetching interviews for job ${jobId}`);
        const interviewsData = await interviewsResponse.json();
        setInterviews(interviewsData); // This will now hold interviews for the selected job
        setGlobalError(null);
    } catch (err) {
        console.error(`Failed to fetch details for job ${jobId}:`, err);
        setGlobalError(err.message);
        setSelectedJobDetails(null);
        setInterviews([]);
    } finally {
        setLoadingState('jobDetails', false);
        setLoadingState('interviews', false);
    }
  }, []);

  const fetchInterviewDetails = useCallback(async (interviewId) => {
    if (!interviewId) {
        setSelectedInterviewDetails(null);
        return;
    }
    setLoadingState('interviewDetails', true);
    try {
        const response = await fetch(`${API_BASE_URL}/interviews/${interviewId}`);
        if (!response.ok) {
            if(response.status === 404) setSelectedInterviewDetails(null);
            throw new Error(`HTTP error ${response.status} fetching interview ${interviewId}`);
        }
        const data = await response.json();
        setSelectedInterviewDetails(data);
        setGlobalError(null);
    } catch (err) {
        console.error(`Failed to fetch interview details for ${interviewId}:`, err);
        setGlobalError(err.message);
        setSelectedInterviewDetails(null);
    } finally {
        setLoadingState('interviewDetails', false);
    }
  }, []);


  // Initial data load
  useEffect(() => {
    if (isLoggedIn) {
      fetchDashboardSummary();
      fetchJobs();
      fetchInterviewsForDashboard();
    }
  }, [isLoggedIn, fetchJobs, fetchInterviewsForDashboard, fetchDashboardSummary]);


  // --- Event Handlers ---
  const handleSelectJob = (job) => {
    setSelectedJobId(job.id);
    fetchJobDetailsAndInterviews(job.id); // Fetches job details and its specific interviews
    setSelectedInterviewId(null);
    setSelectedInterviewDetails(null);
  };

  const handleSelectInterview = (interviewId) => {
    setSelectedInterviewId(interviewId);
    fetchInterviewDetails(interviewId);
    setSelectedJobId(null); // Clear selected job when viewing an interview
    setSelectedJobDetails(null);
  };

  const handleBackToDashboard = () => {
    setSelectedJobId(null);
    setSelectedJobDetails(null);
    setSelectedInterviewId(null);
    setSelectedInterviewDetails(null);
    fetchInterviewsForDashboard(); // Refresh all interviews for dashboard view
    fetchJobs();
    fetchDashboardSummary();
    setGlobalError(null);
  };

  const handleOpenNewJobModal = () => {
    setEditingJob(null);
    setIsJobFormModalOpen(true);
  };

  const handleOpenEditJobModal = (job) => {
    setEditingJob(job);
    setIsJobFormModalOpen(true);
  };

  const handleSaveJob = async (jobData, jobIdToUpdate) => {
    const method = jobIdToUpdate ? 'PUT' : 'POST';
    const url = jobIdToUpdate ? `${API_BASE_URL}/jobs/${jobIdToUpdate}` : `${API_BASE_URL}/jobs`;
    try {
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(jobData)
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({message: "Unknown error occurred"}));
            throw new Error(errorData.message || `HTTP error ${response.status}`);
        }
        setIsJobFormModalOpen(false);
        setEditingJob(null);
        fetchJobs();
        fetchDashboardSummary();
        if (selectedJobId && selectedJobId === jobIdToUpdate) {
            fetchJobDetailsAndInterviews(jobIdToUpdate);
        }
        setGlobalError(null); // Clear previous errors on success
    } catch (err) {
        console.error("Failed to save job:", err);
        setGlobalError("Failed to save job: " + err.message);
    }
  };

  const handleDeleteJob = async (jobId) => {
    if (window.confirm("Are you sure you want to delete this job? This action cannot be undone.")) {
        try {
            const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`, { method: 'DELETE' });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({message: "Unknown error occurred"}));
                throw new Error(errorData.message || `HTTP error ${response.status}`);
            }
            fetchJobs();
            fetchDashboardSummary();
            if (selectedJobId === jobId) {
                handleBackToDashboard();
            }
            setGlobalError(null);
        } catch (err) {
            console.error("Failed to delete job:", err);
            setGlobalError("Failed to delete job: " + err.message);
        }
    }
  };

  const handleSaveInterviewFeedback = async (interviewId, score, feedbackText) => {
    try {
        const response = await fetch(`${API_BASE_URL}/interviews/${interviewId}/score`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ score: score, feedback: feedbackText }) // Ensure score can be null
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({message: "Unknown error occurred"}));
            throw new Error(errorData.message || `HTTP error ${response.status}`);
        }
        const updatedInterview = await response.json();
        setSelectedInterviewDetails(updatedInterview);
        setInterviews(prev => prev.map(i => i.id === interviewId ? {...i, ...updatedInterview} : i));
        fetchDashboardSummary();
        setGlobalError(null);
    } catch (err) {
        console.error("Failed to save interview feedback:", err);
        setGlobalError("Failed to save feedback: " + err.message);
    }
  };

  const handleSendInvites = (jobId) => {
    alert(`Placeholder: Send invites for Job ID: ${jobId}`);
  };


  const NavItem = ({ icon, label, isActive, onClick, isDisabled = false }) => (
    <li
      onClick={!isDisabled ? onClick : undefined}
      className={`flex items-center p-3 my-1 rounded-lg transition-colors ${
        isDisabled ? 'text-gray-500 cursor-not-allowed' :
        isActive ? 'bg-indigo-700 text-white' : 'text-gray-300 hover:bg-indigo-500 hover:text-white cursor-pointer'
      }`}
    >
      {icon}
      {isSidebarOpen && <span className="ml-3">{label}</span>}
    </li>
  );

  if (!isLoggedIn) {
     return (
        <div className="flex items-center justify-center h-screen bg-gradient-to-br from-indigo-600 to-purple-600">
            <div className="bg-white p-10 rounded-xl shadow-2xl text-center w-full max-w-md">
                <Briefcase size={48} className="mx-auto text-indigo-600 mb-6" />
                <h1 className="text-3xl font-bold text-gray-800 mb-3">AI Interview Portal</h1>
                <p className="text-gray-600 mb-8">Admin Login</p>
                <button
                    onClick={() => setIsLoggedIn(true)}
                    className="w-full bg-indigo-600 text-white py-3 rounded-lg hover:bg-indigo-700 transition-colors text-lg font-semibold"
                >
                    Login (Demo)
                </button>
                {userId && <p className="text-xs text-gray-500 mt-4">Logged in as: {userId}</p>}
            </div>
        </div>
    );
  }

  let currentViewTitle = "Admin Dashboard";
  if (selectedJobDetails) currentViewTitle = `Job: ${selectedJobDetails.title}`;
  else if (selectedInterviewDetails) currentViewTitle = `Interview: ${selectedInterviewDetails.candidate_name || 'Details'}`;

  return (
    <div className="flex h-screen bg-gray-100 font-inter">
      <aside className={`bg-indigo-800 text-white transition-all duration-300 ease-in-out ${isSidebarOpen ? 'w-64' : 'w-20'} flex flex-col`}>
        <div className="flex items-center justify-between p-4 h-16 border-b border-indigo-700">
           {isSidebarOpen && <span className="text-xl font-semibold">AI Portal</span>}
          <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 rounded-md hover:bg-indigo-700 focus:outline-none">
            {isSidebarOpen ? <ChevronRight size={20} className="transform rotate-180"/> : <ChevronRight size={20} />}
          </button>
        </div>
        <nav className="flex-grow p-2">
          <ul>
            <NavItem icon={<BarChart2 size={20} />} label="Dashboard" isActive={!selectedJobId && !selectedInterviewId} onClick={handleBackToDashboard} />
            {/* These are simplified nav items. Active state could be more granular. */}
            <NavItem icon={<Briefcase size={20} />} label="Job Postings" isActive={selectedJobId !== null && !selectedInterviewId} onClick={handleBackToDashboard} />
            <NavItem icon={<Calendar size={20} />} label="Interviews" isActive={selectedInterviewId !== null} onClick={handleBackToDashboard} />
            <NavItem icon={<Users size={20} />} label="Candidates" isDisabled={true} />
            <NavItem icon={<Send size={20} />} label="Invitations" isDisabled={true} />
          </ul>
        </nav>
        <div className="p-2 border-t border-indigo-700">
          {isSidebarOpen && userId && <p className="text-xs text-indigo-300 p-2 truncate" title={userId}>User: {userId}</p>}
          <NavItem icon={<Settings size={20} />} label="Settings" isDisabled={true}/>
          <NavItem icon={<LogOut size={20} />} label="Logout" onClick={() => setIsLoggedIn(false)} />
        </div>
      </aside>

      <main className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto">
        <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 sm:mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-800 truncate max-w-md">{currentViewTitle}</h1>
            <p className="text-gray-500 text-sm">Welcome back, Admin!</p>
          </div>
          <div className="flex items-center space-x-2 sm:space-x-4 mt-2 sm:mt-0">
            <div className="relative">
              <input type="text" placeholder="Search..." className="pl-10 pr-4 py-2 w-full sm:w-64 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 text-sm"/>
              <Search size={18} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400"/>
            </div>
            <button className="p-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
              <Filter size={20} className="text-gray-600"/>
            </button>
          </div>
        </header>

        {globalError && <AlertMessage message={globalError} type="error" onDismiss={() => setGlobalError(null)} />}

        {(isLoading.dashboard || isLoading.jobs || isLoading.interviews || isLoading.jobDetails || isLoading.interviewDetails) &&
         (!selectedJobId && !selectedInterviewId && !globalError) &&
            <div className="text-center py-10"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div><p className="text-lg text-gray-500 mt-4">Loading data...</p></div>
        }

        {!isLoading.dashboard && !isLoading.jobs && !isLoading.interviews && !isLoading.jobDetails && !isLoading.interviewDetails && !globalError && (
            selectedInterviewId && selectedInterviewDetails ? (
              <InterviewDetailView
                interviewDetails={selectedInterviewDetails}
                onBack={handleBackToDashboard}
                onSaveFeedback={handleSaveInterviewFeedback}
                isLoading={isLoading.interviewDetails}
              />
            ) : selectedJobId && selectedJobDetails ? (
              <JobDetailView
                job={selectedJobDetails}
                interviewsForJob={interviews}
                onBack={handleBackToDashboard}
                onSelectInterview={handleSelectInterview}
                onEditJob={handleOpenEditJobModal}
                onSendInvites={handleSendInvites}
                isLoading={isLoading.jobDetails || isLoading.interviews}
              />
            ) : (
              <>
                <DashboardOverview summaryData={dashboardSummary} isLoading={isLoading.dashboard} />
                <JobList
                    jobs={jobs}
                    onSelectJob={handleSelectJob}
                    onAddNewJob={handleOpenNewJobModal}
                    onDeleteJob={handleDeleteJob}
                    onEditJob={handleOpenEditJobModal}
                    isLoading={isLoading.jobs}
                />
                <InterviewList
                    interviews={interviews}
                    onSelectInterview={handleSelectInterview}
                    isLoading={isLoading.interviews}
                />
              </>
            )
        )}
         {/* Fallback for when loading is done but no specific view is selected and there might have been an error during a specific fetch */}
        {!isLoading.dashboard && !isLoading.jobs && !isLoading.interviews && !selectedJobId && !selectedInterviewId && globalError &&
            <div className="text-center py-10">
                <AlertCircle size={48} className="mx-auto text-red-500 mb-4" />
                <p className="text-lg text-red-700">Could not load all dashboard components.</p>
                <p className="text-sm text-gray-600">{globalError}</p>
            </div>
        }

      </main>
      <JobFormModal
        isOpen={isJobFormModalOpen}
        onClose={() => { setIsJobFormModalOpen(false); setEditingJob(null); }}
        onSaveJob={handleSaveJob}
        jobToEdit={editingJob}
      />
    </div>
  );
};

export default App;
